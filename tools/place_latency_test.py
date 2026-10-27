"""Latence d'apparition / de disparition d'une pièce posée au marteau (client de protocole, sans interface).
Mesure le temps entre l'envoi de `.build api placeat` et l'arrivée du SMSG_UPDATE_OBJECT qui crée le GameObject chez le joueur,
puis entre le clic droit de démolition et le SMSG_DESTROY_OBJECT / bloc hors de portée. Critère : < 200 ms en local.
python place_latency_test.py <compte> <mdp> [répétitions]   (compte GM, serveur lancé, personnage 'Wlcost')"""
import struct, sys, time, zlib, socket
from wlclient import Session, login_char, goto_test_spot

SMSG_UPDATE_OBJECT, SMSG_COMPRESSED_UPDATE_OBJECT, SMSG_DESTROY_OBJECT = 0x0A9, 0x1F6, 0x0AA
SMSG_GAMEOBJECT_DESPAWN_ANIM = 0x215
PIECE_ID = 6                       # table de fabrication : n'exige aucune station
GO_ENTRY = 9110000 + PIECE_ID
LIMIT_MS = 200.0
REPS = int(sys.argv[3]) if len(sys.argv) > 3 else 3


def go_guid(low):
    return (0xF110 << 48) | (GO_ENTRY << 24) | low


def payload(op, d):
    if op == SMSG_COMPRESSED_UPDATE_OBJECT:
        return zlib.decompress(d[4:])
    return d


def guids_in(blob):
    """GUID complets (8 octets, haut = 0xF110, entrée = GO_ENTRY) présents dans un paquet de mise à jour (champ OBJECT_FIELD_GUID)."""
    out = set()
    tail = struct.pack("<Q", go_guid(0))[3:]      # octets 3..7 : entrée + haut
    i = blob.find(tail)
    while i != -1:
        if i >= 3:
            out.add(struct.unpack("<Q", blob[i - 3:i + 5])[0] & 0xFFFFFF)
        i = blob.find(tail, i + 1)
    return out


def pump(s, until, on_packet, timeout):
    """Lit les paquets jusqu'à ce que `until()` soit vrai ou le délai écoulé ; on_packet(op, data, t)."""
    end = time.perf_counter() + timeout
    s.s.settimeout(0.05)
    while time.perf_counter() < end and not until():
        try:
            op, d = s.read()
        except socket.timeout:
            continue
        on_packet(op, d, time.perf_counter())


s = Session(sys.argv[1], sys.argv[2]); login_char(s, "Wlcost"); goto_test_spot(s)
def say(c, t=0.8): return [l for l in s.say(c, t) if "Welcome to" not in l and "Tickets" not in l]
say(".build nocost on"); say(".build api mode build")
ok = True
x0, y0 = -6180.0, 745.0
gps = " ".join(say(".gps", 1.0))
import re
m = re.search(r"X: ([-\d.]+) Y: ([-\d.]+) Z: ([-\d.]+)", gps)
x0, y0, z0 = (float(m[1]), float(m[2]), float(m[3])) if m else (x0, y0, 400.0)

say(".additem 9201100 1", 1.0); time.sleep(0.3); s.equip_item(9201100); time.sleep(1.0)   # marteau en main droite

for rep in range(REPS * 2):
    via_spell = rep % 2 == 1        # une pose sur deux : vrai chemin du jeu (utilisation du marteau -> sort 40001 à cible au sol)
    say(f".build api select {PIECE_ID} 0")
    st = {"reply": None, "create": None, "low": None}
    def on_place(op, d, t):
        if op == 0x96 and d[0] == 10:
            ln = struct.unpack("<I", d[13:17])[0]
            txt = d[17:17 + ln - 1].decode("utf-8", "replace")
            if "D|place|" in txt and st["reply"] is None:
                st["reply"] = (t, txt)
        elif op in (SMSG_UPDATE_OBJECT, SMSG_COMPRESSED_UPDATE_OBJECT) and st["create"] is None:
            found = guids_in(payload(op, d))
            if found:
                st["create"], st["low"] = t, min(found)
    t0 = time.perf_counter()
    px, py, pz = x0 + 4, y0 + (rep % 3) * 2 - 2, z0
    if via_spell:   # CMSG_USE_ITEM : sac 255, emplacement 15 (main droite), sort 0, cibles = TARGET_FLAG_DEST_LOCATION (0x40) + x y z
        s.send(0x0AB, struct.pack("<BBBHfff", 255, 15, 0, 0x40, px, py, pz))
    else:
        s.say(f".build api placeat {px:.2f} {py:.2f} {pz:.2f}", 0)
    pump(s, lambda: st["create"] is not None and st["reply"] is not None, on_place, 6.0)
    if st["reply"] is None or "D|place|1" not in st["reply"][1]:
        print("[ÉCHEC] pose refusée :", st["reply"]); ok = False; continue
    if st["create"] is None:
        print("[ÉCHEC] aucune création de GameObject reçue en 6 s"); ok = False; continue
    dt_c = (st["create"] - t0) * 1000.0
    dt_r = (st["reply"][0] - t0) * 1000.0
    good = dt_c < LIMIT_MS; ok &= good
    print(("[OK]   " if good else "[ÉCHEC]"), f"pose #{rep + 1} ({'sort du marteau' if via_spell else 'placeat'}) : création visible {dt_c:.0f} ms (réponse serveur {dt_r:.0f} ms, création - réponse {dt_c - dt_r:+.0f} ms) guid {st['low']}", flush=True)

    # démolition (clic droit en mode démolir)
    say(".build api mode remove")
    low, full = st["low"], go_guid(st["low"])
    dst = {"gone": None}
    def on_remove(op, d, t):
        if dst["gone"] is not None:
            return
        if op == SMSG_DESTROY_OBJECT and struct.unpack("<Q", d[:8])[0] == full:
            dst["gone"] = t
        elif op in (SMSG_UPDATE_OBJECT, SMSG_COMPRESSED_UPDATE_OBJECT):
            b = payload(op, d)
            # bloc hors de portée (type 4) : GUID compactés ; on cherche le GUID compacté de la pièce
            mask, packed = 0, b""
            for i, byte in enumerate(struct.pack("<Q", full)):
                if byte:
                    mask |= 1 << i; packed += bytes([byte])
            if bytes([mask]) + packed in b and b.find(b"\x04") != -1 and full not in [go_guid(g) for g in guids_in(b)]:
                dst["gone"] = t
    t1 = time.perf_counter()
    s.send(0x0B1, struct.pack("<Q", full))       # CMSG_GAMEOBJ_USE
    pump(s, lambda: dst["gone"] is not None, on_remove, 6.0)
    say(".build api mode build", 0.3)
    if dst["gone"] is None:
        print("[ÉCHEC] démolition : aucune destruction reçue en 6 s"); ok = False; continue
    dt_d = (dst["gone"] - t1) * 1000.0
    good = dt_d < LIMIT_MS; ok &= good
    print(("[OK]   " if good else "[ÉCHEC]"), f"démolition #{rep + 1} : disparition {dt_d:.0f} ms", flush=True)

say(".build nocost off")
s.close()
print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
