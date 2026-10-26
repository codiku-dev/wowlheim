"""Applique les scripts SQL de Wowlheim dans l'ordre : server/sql/world/*.sql -> classicmangos, server/sql/characters/*.sql -> classiccharacters.
Option --backup : sauvegarde d'abord classicmangos et classiccharacters dans C:/Wowlheim/backup. MySQL local uniquement."""
import glob, os, subprocess, sys, time
BIN = r"C:\Program Files\MySQL\MySQL Server 8.4\bin"
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server", "sql")
def mysql(db, path):
    with open(path, "rb") as f:
        r = subprocess.run([BIN + r"\mysql.exe", "--user=root", "--host=127.0.0.1", "--default-character-set=utf8mb4", db], stdin=f, capture_output=True)
    if r.returncode:
        raise SystemExit(f"ERREUR {path} : {r.stderr.decode('utf-8', 'replace')}")
if "--backup" in sys.argv:
    os.makedirs(r"C:/Wowlheim/backup", exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for db in ("classicmangos", "classiccharacters"):
        dst = rf"C:/Wowlheim/backup\{db}_{stamp}.sql"
        with open(dst, "wb") as f:
            subprocess.run([BIN + r"\mysqldump.exe", "--user=root", "--host=127.0.0.1", "--default-character-set=utf8mb4", "--single-transaction", db], stdout=f, check=True)
        print("sauvegarde", dst, os.path.getsize(dst), "octets")
for db, sub in (("classicmangos", "world"), ("classiccharacters", "characters")):
    for p in sorted(glob.glob(os.path.join(BASE, sub, "*.sql"))):
        print(sub, os.path.basename(p), flush=True)
        mysql(db, p)
print("terminé")
