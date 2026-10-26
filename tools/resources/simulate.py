"""Simulation (Monte-Carlo) du butin Wowlheim d'une creature, d'apres les LIGNES REELLES de la base.
Reprend la semantique de LootTemplate::Process lue dans le code du serveur (Loot/LootMgr.cpp) : entrees non groupees tirees
independamment ; reference = Process(reference) repete `maxcount` fois ; chance >= 100 -> toujours. Ce n'est PAS le serveur lui-meme.

usage : python simulate.py <entry de creature> [kills=20000] [--db BASE]"""
import os, sys, random, collections
sys.path.insert(0, os.path.dirname(__file__))
from common import sql
import rules

args = [a for a in sys.argv[1:] if not a.startswith("--")]
db = "classicmangos"
if "--db" in sys.argv:
    db = sys.argv[sys.argv.index("--db") + 1]
    args = [a for a in args if a != db]
entry = int(args[0])
n = int(args[1]) if len(args) > 1 else 20000
c = sql("select Name,MinLevel,MaxLevel,`Rank`,LootId from creature_template where Entry=%d" % entry, db)[0]
lootid = int(c[4])
rows = [(int(a), float(b), int(m), int(x)) for a, b, m, x in sql("select item,ChanceOrQuestChance,mincountOrRef,maxcount from creature_loot_template where entry=%d and groupid=0" % lootid, db)]
refs = collections.defaultdict(list)
for e, i, ch, mn, mx in sql("select entry,item,ChanceOrQuestChance,mincountOrRef,maxcount from reference_loot_template where entry between %d and %d and groupid=0" % (rules.REF_BASE, rules.REF_BASE + 99999), db):
    refs[int(e)].append((int(i), float(ch), int(mn), int(mx)))
got = collections.Counter()
qty = collections.Counter()
for _ in range(n):
    for item, ch, mn, mx in rows:
        if mn < 0 and -mn >= rules.REF_BASE:
            if ch < 100 and random.random() * 100 >= ch:
                continue
            for _r in range(mx):
                for it, c2, a, b in refs[-mn]:
                    if c2 >= 100 or random.random() * 100 < c2:
                        got[it] += 1
                        qty[it] += random.randint(a, b)
print("%s (entry %d, niveau %s-%s, rang %s, LootId %d) : %d morts simulees ; lignes Wowlheim : %d" % (c[0], entry, c[1], c[2], c[3], lootid, n,
      sum(1 for r in rows if r[2] < 0 and -r[2] >= rules.REF_BASE)))
for it, k in sorted(got.items()):
    print("  %-18s %5.1f %% des morts, %.2f par mort en moyenne" % (rules.MAT[it]["name"], 100.0 * k / n, qty[it] / n))
