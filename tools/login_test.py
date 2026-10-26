"""Client de test minimal 1.12.1 (build 5875) : logon SRP6, realmlist, auth monde, CHAR_ENUM.
Local uniquement. Usage: python -I login_test.py <compte> <mot_de_passe>"""
import hashlib, os, socket, struct, sys, zlib

N = int("894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7", 16)
G = 7
sha1 = lambda *p: hashlib.sha1(b"".join(p)).digest()
le = lambda b: int.from_bytes(b, "little")
tob = lambda n, l=32: n.to_bytes(l, "little")


def recv_exact(s, n):
    d = b""
    while len(d) < n:
        c = s.recv(n - len(d))
        if not c:
            raise EOFError("connexion fermée")
        d += c
    return d


def logon(user, pw):
    s = socket.create_connection(("127.0.0.1", 3724), timeout=10)
    u = user.upper().encode()
    body = b"WoW\0" + bytes([1, 12, 1]) + struct.pack("<H", 5875) + b"68x\0" + b"niW\0" + b"SUne" + struct.pack("<I", 60) + struct.pack("<I", 0x0100007F) + bytes([len(u)]) + u
    s.sendall(bytes([0, 3]) + struct.pack("<H", len(body)) + body)
    h = recv_exact(s, 3)
    if h[2] != 0:
        raise SystemExit(f"logon challenge refusé, code {h[2]}")
    B = le(recv_exact(s, 32)); gl = recv_exact(s, 1)[0]; g = le(recv_exact(s, gl))
    nl = recv_exact(s, 1)[0]; n = le(recv_exact(s, nl)); salt = recv_exact(s, 32); recv_exact(s, 16); recv_exact(s, 1)
    assert g == G and n == N
    a = le(os.urandom(19)); A = pow(G, a, N)
    x = le(sha1(salt, sha1(u + b":" + pw.upper().encode())))
    uu = le(sha1(tob(A), tob(B)))
    S = pow((B - 3 * pow(G, x, N)) % N, a + uu * x, N)
    St = tob(S)
    K = b"".join(bytes(t) for t in zip(sha1(St[0::2]), sha1(St[1::2])))
    t3 = bytes(a ^ b for a, b in zip(sha1(tob(N)), sha1(tob(G, 1))))
    M1 = sha1(t3, sha1(u), salt, tob(A), tob(B), K)
    s.sendall(bytes([1]) + tob(A) + M1 + b"\0" * 20 + b"\0\0")
    h = recv_exact(s, 2)
    if h[1] != 0:
        raise SystemExit(f"preuve refusée, code {h[1]} (mauvais compte/mot de passe ?)")
    recv_exact(s, 20 + 4)
    print("[realmd] authentification SRP6 OK")
    s.sendall(bytes([0x10]) + b"\0" * 4)
    cmd = recv_exact(s, 1)[0]; size = struct.unpack("<H", recv_exact(s, 2))[0]; data = recv_exact(s, size)
    cnt = data[4]
    rest = data[5:]; i = rest.index(b"\0", 3); name = rest[3:i].decode(); j = rest.index(b"\0", i + 1); addr = rest[i + 1:j].decode()
    print(f"[realmd] realmlist: {cnt} royaume(s): {name} @ {addr}")
    s.close()
    return K, u, addr


class Crypt:
    def __init__(self, key):
        self.k = key; self.si = self.sj = self.ri = self.rj = 0

    def enc(self, d):
        o = bytearray(d)
        for t in range(len(o)):
            self.si %= len(self.k); x = ((o[t] ^ self.k[self.si]) + self.sj) & 0xFF; self.si += 1; o[t] = self.sj = x
        return bytes(o)

    def dec(self, d):
        o = bytearray(d)
        for t in range(len(o)):
            self.ri %= len(self.k); x = ((o[t] - self.rj) & 0xFF) ^ self.k[self.ri]; self.ri += 1; self.rj = o[t]; o[t] = x
        return bytes(o)


def addons():
    raw = b"Blizzard_TestAddon\0" + bytes([1]) + struct.pack("<II", 0x4C1C776D, 0)
    return struct.pack("<I", len(raw)) + zlib.compress(raw)


def world(K, u):
    s = socket.create_connection(("127.0.0.1", 8085), timeout=10)
    h = recv_exact(s, 4)
    size = struct.unpack(">H", h[:2])[0]; op = struct.unpack("<H", h[2:])[0]
    seed = recv_exact(s, size - 2)
    assert op == 0x1EC, hex(op)
    cseed = os.urandom(4)
    digest = sha1(u, b"\0\0\0\0", cseed, seed[:4], K)
    body = struct.pack("<II", 5875, 0) + u + b"\0" + cseed + digest + addons()
    pkt = struct.pack(">H", len(body) + 4) + struct.pack("<I", 0x1ED) + body
    s.sendall(pkt)
    c = Crypt(K)
    def pkt(want):
        while True:
            hd = c.dec(recv_exact(s, 4)); size = struct.unpack(">H", hd[:2])[0]; op = struct.unpack("<H", hd[2:])[0]
            data = recv_exact(s, size - 2)
            if op == want:
                return op, data
            print(f"[mangosd] (ignoré opcode 0x{op:03X}, {len(data)} o)")
    op, data = pkt(0x1EE)
    print(f"[mangosd] AUTH_RESPONSE code 0x{data[0]:02X} ({'OK' if data[0] == 0x0C else 'ÉCHEC'})")
    if data[0] != 0x0C:
        return
    s.sendall(c.enc(struct.pack(">H", 4) + struct.pack("<I", 0x37)))
    op, data = pkt(0x03B)
    print(f"[mangosd] opcode reçu 0x{op:03X} (CHAR_ENUM=0x03B), {data[0]} personnage(s)")
    s.close()


if __name__ == "__main__":
    K, u, addr = logon(sys.argv[1], sys.argv[2])
    world(K, u)
