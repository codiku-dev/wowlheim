"""Mini-client de test 1.12.1 (local) : crée un personnage, entre dans le monde, envoie des commandes de chat, lit les réponses.
Usage en bibliothèque : from wlclient import Session
Sans GUI : sert à tester les commandes serveur (.build ...) de bout en bout. Local uniquement (127.0.0.1)."""
import socket, struct, time, zlib, os
from login_test import logon, Crypt, recv_exact, sha1, addons

OP_AUTH_CHALLENGE, OP_AUTH_SESSION, OP_AUTH_RESPONSE = 0x1EC, 0x1ED, 0x1EE
OP_CHAR_ENUM, OP_CHAR_CREATE, OP_PLAYER_LOGIN = 0x37, 0x36, 0x3D
OP_MESSAGECHAT, OP_SMSG_MESSAGECHAT = 0x95, 0x96
OP_SMSG_CHAR_ENUM, OP_SMSG_CHAR_CREATE, OP_LOGIN_VERIFY_WORLD = 0x3B, 0x3A, 0x236


class Session:
    def __init__(self, user, pw):
        self.user = user
        for attempt in range(4):             # le SRP6 échoue très rarement (zéros de tête dans A/B/sel) : on réessaie
            try:
                K, u, _ = logon(user, pw)
                break
            except SystemExit:
                if attempt == 3:
                    raise
        s = socket.create_connection(("127.0.0.1", 8085), timeout=10)
        h = recv_exact(s, 4)
        size = struct.unpack(">H", h[:2])[0]
        seed = recv_exact(s, size - 2)
        cseed = os.urandom(4)
        digest = sha1(u, b"\0\0\0\0", cseed, seed[:4], K)
        body = struct.pack("<II", 5875, 0) + u + b"\0" + cseed + digest + addons()
        s.sendall(struct.pack(">H", len(body) + 4) + struct.pack("<I", 0x1ED) + body)
        self.s, self.c = s, Crypt(K)
        op, data = self.wait(OP_AUTH_RESPONSE)
        if data[0] != 0x0C:
            raise RuntimeError(f"auth monde refusée 0x{data[0]:02X}")
        self.buffer = []

    def send(self, op, payload=b""):
        self.s.sendall(self.c.enc(struct.pack(">H", len(payload) + 4) + struct.pack("<I", op)) + payload)

    def read(self):
        hd = self.c.dec(recv_exact(self.s, 4))
        size = struct.unpack(">H", hd[:2])[0]
        op = struct.unpack("<H", hd[2:])[0]
        data = recv_exact(self.s, size - 2)
        if op == 0x166 and len(data) >= 29:       # SMSG_ITEM_PUSH_RESULT : retient (sac, emplacement) de chaque objet reçu
            if not hasattr(self, "pushes"):
                self.pushes = {}
            self.pushes[struct.unpack("<I", data[25:29])[0]] = (data[20], struct.unpack("<I", data[21:25])[0])
        return op, data

    def wait(self, want, timeout=15):
        end = time.time() + timeout
        self.s.settimeout(timeout)
        while time.time() < end:
            op, data = self.read()
            if op == want:
                return op, data
        raise TimeoutError(hex(want))

    def chars(self):
        self.send(OP_CHAR_ENUM)
        _, d = self.wait(OP_SMSG_CHAR_ENUM)
        out, n, i = [], d[0], 1
        for _ in range(n):
            guid = struct.unpack("<Q", d[i:i + 8])[0]; i += 8
            j = d.index(b"\0", i); name = d[i:j].decode(); i = j + 1
            i += 9 + 4 + 4 + 12 + 4 + 4 + 1 + 12 + 100  # race..level(9), zone, map, xyz, guild, flags, firstlogin, pet(12), equipement(100)
            out.append((guid, name))
        return out

    def create(self, name, race=1, cls=1, gender=0):
        self.send(OP_CHAR_CREATE, name.encode() + b"\0" + bytes([race, cls, gender, 0, 0, 0, 0, 0, 0]))
        _, d = self.wait(OP_SMSG_CHAR_CREATE)
        return d[0]  # 0x2E = succès

    def login(self, guid):
        self.guid = guid
        self.send(OP_PLAYER_LOGIN, struct.pack("<Q", guid))
        self.wait(OP_LOGIN_VERIFY_WORLD)

    def say(self, text, collect=1.5):
        """Envoie du texte en /dire ; renvoie les lignes de chat système reçues pendant `collect` secondes."""
        self.send(OP_MESSAGECHAT, struct.pack("<II", 0, 0) + text.encode() + b"\0")
        lines, end = [], time.time() + collect
        self.s.settimeout(0.5)
        while time.time() < end:
            try:
                op, d = self.read()
            except socket.timeout:
                continue
            if op == OP_SMSG_MESSAGECHAT and d[0] == 10:
                ln = struct.unpack("<I", d[13:17])[0]
                lines.append(d[17:17 + ln - 1].decode("utf-8", "replace"))
        return lines

    def teleport(self, place, timeout=8):
        """GM : `.tele <lieu>` puis acquittement du téléport comme le ferait le client (sinon le serveur garde le joueur en transit)."""
        return self.teleport_cmd(".tele " + place, timeout)

    def teleport_cmd(self, command, timeout=8):
        self.send(OP_MESSAGECHAT, struct.pack("<II", 0, 0) + command.encode() + bytes([0]))
        end, done = time.time() + timeout, False
        self.s.settimeout(0.8)
        while time.time() < end:
            try:
                op, d = self.read()
            except socket.timeout:
                if done:
                    break
                continue
            if op == 0x0C7:        # MSG_MOVE_TELEPORT_ACK (même carte)
                mask = d[0]; i = 1
                for b in range(8):
                    if mask & (1 << b): i += 1
                counter = struct.unpack("<I", d[i:i + 4])[0]
                self.send(0x0C7, struct.pack("<QII", self.guid, counter, int(time.time() * 1000) & 0xFFFFFFFF))
                done = True
            elif op == 0x03E:      # SMSG_NEW_WORLD (autre carte)
                self.send(0x0DC)   # MSG_MOVE_WORLDPORT_ACK
                done = True
        time.sleep(1.0)
        return done

    def use_gameobject(self, entry, low, collect=1.5):
        """CMSG_GAMEOBJ_USE puis lecture : renvoie (notifications, objets_du_butin) ; ouvre le butin (SMSG_LOOT_RESPONSE) si présent."""
        guid = (0xF110 << 48) | (entry << 24) | low
        self.send(0x0B1, struct.pack("<Q", guid))
        notes, items, end = [], [], time.time() + collect
        self.s.settimeout(0.5)
        while time.time() < end:
            try:
                op, d = self.read()
            except socket.timeout:
                continue
            if op == 0x1CB:       # SMSG_NOTIFICATION
                notes.append(d.split(b"\0")[0].decode("utf-8", "replace"))
            elif op == 0x160:     # SMSG_LOOT_RESPONSE
                n = d[8 + 1 + 4]
                i = 8 + 1 + 4 + 1
                for _ in range(n):
                    slot = d[i]; item = struct.unpack("<I", d[i + 1:i + 5])[0]; cnt = struct.unpack("<I", d[i + 5:i + 9])[0]
                    items.append((slot, item, cnt)); i += 1 + 4 + 4 + 4 + 4 + 4 + 1
        return notes, items

    def autostore_loot(self, slot):
        self.send(0x108, bytes([slot]))   # CMSG_AUTOSTORE_LOOT_ITEM

    def release_loot(self, entry, low):
        self.send(0x15F, struct.pack("<Q", (0xF110 << 48) | (entry << 24) | low))   # CMSG_LOOT_RELEASE

    def equip_item(self, item_id):
        bag, slot = getattr(self, "pushes", {}).get(item_id, (255, 23))
        self.send(0x10A, bytes([bag, slot]))            # CMSG_AUTOEQUIP_ITEM (sac, emplacement)

    def close(self):
        self.s.close()


def login_char(session, name):
    """Entre dans le monde avec le personnage `name` (créé s'il n'existe pas : humain guerrier, sac vide)."""
    chars = {nm: g for g, nm in session.chars()}
    if name not in chars:
        session.create(name)
        chars = {nm: g for g, nm in session.chars()}
    session.login(chars[name])
    return chars[name]


def goto_test_spot(session, x=-6180.0, y=745.0, z=400.0):
    """Place le personnage sur un terrain libre hors villages (Coldridge Valley) et le ressuscite."""
    session.say(".gm on", 0.4)                 # mode GM : les créatures n'attaquent pas le personnage de test
    import re as _re
    session.teleport_cmd(f".go xyz {x} {y} {z} 0")
    time.sleep(3.0)
    session.say(".revive", 0.6)
    gps = " ".join(session.say(".gps", 1.0))
    m = _re.search(r"GroundZ: ([-\d.]+)", gps)
    if m:                                      # se poser exactement sur le sol (en mode GM le personnage ne tombe pas)
        session.teleport_cmd(f".go xyz {x} {y} {float(m.group(1)) + 0.2} 0")
        time.sleep(2.0)
