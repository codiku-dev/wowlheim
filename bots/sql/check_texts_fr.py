"""Verifie la traduction FR de ai_playerbot_texts (base classicmangos_bots).

Usage : python -I check_texts_fr.py [--mysql CHEMIN] [--db classicmangos_bots]

- compte les lignes sans text_loc2 (FR) ;
- verifie que les placeholders (%xxx, <xxx>, liens |c...|r, %) sont identiques
  entre `text` et `text_loc2` ;
- si ai_playerbot_texts_en_backup.sql est present a cote : verifie aussi les
  placeholders entre l'anglais d'origine et `text`, et compte les lignes dont
  `text` est encore identique a l'anglais.
Code de sortie 0 si aucun ecart de placeholder.
"""
import argparse
import os
import re
import subprocess
import sys
from collections import Counter

TOK = re.compile(r'%[A-Za-z_]+|<[^<>]+>|\|c[0-9a-fA-F]{8}|\|r|@#\$@%|#!@|%')
DEFAULT_MYSQL = r'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP_RE = re.compile(r"^UPDATE `ai_playerbot_texts` SET `text`='((?:[^'\\]|\\.)*)', "
                       r"`text_loc2`='(?:[^'\\]|\\.)*' WHERE `id`=(\d+);$")


def unescape(s):
    return re.sub(r'\\(.)', r'\1', s)


def toks(s):
    return Counter(TOK.findall(s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mysql', default=DEFAULT_MYSQL)
    ap.add_argument('--db', default='classicmangos_bots')
    a = ap.parse_args()
    if not a.db.endswith('_bots'):
        sys.exit('refus : base sans suffixe _bots')

    out = subprocess.run(
        [a.mysql, '-uroot', '-h127.0.0.1', '-N', '-B', a.db, '-e',
         'SELECT id, HEX(text), HEX(text_loc2) FROM ai_playerbot_texts ORDER BY id'],
        capture_output=True, check=True).stdout.decode('ascii')
    rows = {}
    for line in out.splitlines():
        p = line.split('\t')
        rows[int(p[0])] = (bytes.fromhex(p[1]).decode('utf-8'),
                           bytes.fromhex(p[2]).decode('utf-8') if len(p) > 2 and p[2] != 'NULL' else '')

    en = {}
    bpath = os.path.join(HERE, 'ai_playerbot_texts_en_backup.sql')
    if os.path.exists(bpath):
        for line in open(bpath, encoding='utf-8'):
            m = BACKUP_RE.match(line.rstrip('\n'))
            if m:
                en[int(m.group(2))] = unescape(m.group(1))

    no_fr = [i for i, (t, l2) in rows.items() if not l2.strip()]
    mism = [i for i, (t, l2) in rows.items() if l2.strip() and toks(t) != toks(l2)]
    mism_en = [i for i, (t, _) in rows.items() if i in en and toks(en[i]) != toks(t)]
    same_en = [i for i, (t, _) in rows.items() if i in en and en[i] == t]

    print(f'lignes totales                         : {len(rows)}')
    print(f'lignes sans text_loc2 (FR)             : {len(no_fr)}')
    print(f'placeholders text != text_loc2         : {len(mism)}')
    if en:
        print(f'placeholders anglais d\'origine != text : {len(mism_en)}')
        print(f'text identique a l\'anglais d\'origine   : {len(same_en)} (abreviations universelles : lol, brb, GL...)')
    for i in (mism + mism_en)[:30]:
        t, l2 = rows[i]
        print(f'  ECART id={i}\n    text : {t}\n    loc2 : {l2}\n    en   : {en.get(i, "?")}')
    return 1 if (mism or mism_en) else 0


if __name__ == '__main__':
    sys.exit(main())
