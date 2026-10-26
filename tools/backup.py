"""Sauvegarde des bases de Wowlheim (MySQL local) dans C:/Wowlheim/backup, avec rotation.
Par défaut : characters + realmd (état des joueurs et des pièces posées). --world ajoute classicmangos (84 Mo, reconstructible
depuis classic-db + server/sql, donc facultatif). python tools/backup.py [--world] [--keep N]"""
import glob, os, subprocess, sys, time
BIN = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe"
DEST = r"C:\Wowlheim\backup"
keep = int(sys.argv[sys.argv.index("--keep") + 1]) if "--keep" in sys.argv else 14
dbs = ["classiccharacters", "classicrealmd", "classiclogs"] + (["classicmangos"] if "--world" in sys.argv else [])
os.makedirs(DEST, exist_ok=True)
stamp = time.strftime("%Y%m%d_%H%M%S")
for db in dbs:
    path = os.path.join(DEST, f"{db}_{stamp}.sql")
    with open(path, "wb") as f:
        subprocess.run([BIN, "--user=root", "--host=127.0.0.1", "--default-character-set=utf8mb4", "--single-transaction", db], stdout=f, check=True)
    print("sauvegarde", path, os.path.getsize(path), "octets")
    olds = sorted(glob.glob(os.path.join(DEST, f"{db}_*.sql")))
    for old in olds[:-keep]:
        os.remove(old); print("supprimé", old)
