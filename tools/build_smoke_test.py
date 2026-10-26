"""Test de fumée construction : python -I build_smoke_test.py <compte> <mdp> [commandes...]"""
import sys
from wlclient import Session

s = Session(sys.argv[1], sys.argv[2])
chars = s.chars()
if not chars:
    print("création du personnage Wlbuilder ->", hex(s.create("Wlbuilder")))
    chars = s.chars()
guid, name = chars[0]
print("personnage :", name)
s.login(guid)
cmds = sys.argv[3:] or [".build list", ".build count", ".build place Plancher", ".build count", ".build near 30"]
for c in cmds:
    print(">", c)
    for line in s.say(c):
        print("   ", line)
s.close()
