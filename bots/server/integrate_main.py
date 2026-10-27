#!/usr/bin/env python3
"""Integre playerbots (+ patch Wowlheim des bots) a un arbre CMaNGOS-classic qui porte deja Wowlheim.

Rejouable, etape par etape (--steps), avec --dry-run pour tout afficher sans rien ecrire. Tout ce qui vient du depot
(server/core.patch, server/Wowlheim, server/sql, bots/playerbots.patch, bots/sql) est relu a chaque execution.

  core      : (essai, hors defaut) arbre neuf = clone de --core-src + server/core.patch + server/Wowlheim/* ;
              arbre existant = recopie de server/Wowlheim/* (comme tools/sync_server.ps1).
  module    : <core>/src/modules/PlayerBots = clone de --module-src au commit --module-commit + git apply de
              bots/playerbots.patch ; deja applique -> rien ; puis comparaison fichier par fichier avec --reference
              (arbre du serveur de test des bots).
  cmake     : affiche (ne lance pas) les commandes CMake / build.
  sql       : sauvegarde mysqldump des bases cibles, (--valheim-sql : server/sql/* rejoues), puis tables ai_playerbot_* du module (monde + personnages),
              textes FR de bots/sql, copie des caches depuis --cache-src (evite ~1 h au premier demarrage),
              realmlist (--realm-port / --realm-name) ; controle final contre --compare-world.
  conf      : <run>/mangosd.conf et realmd.conf EXISTANTS modifies au strict necessaire (bases + suffixe, ports,
              LogsDir hors de <run>) ; aiplayerbot.conf, anticheat.conf, ahbot.conf (<run> et <run>\\..\\etc) via
              setup_run.write_bot_confs (memes surcharges que le serveur de test, LLM -> 127.0.0.1:--bridge-port).
  deploy    : copie binaires (--exe) + DLL (build et racine vcpkg) dans <run> (refuse si le binaire tourne).
  shortcut  : lanceur <run>\\lancer_wowlheim_bots.ps1 (serveur + pont LLM) et raccourci .lnk (--shortcut).

Exemples :
  # essai isole
  python -I bots/server/integrate_main.py --core C:\\Wowlheim\\bots\\merged\\mangos-classic --build C:\\Wowlheim\\bots\\build_merged
      --run C:\\Wowlheim\\bots\\run_merged --db-suffix _m --world-port 8086 --realm-port 3725
      --realm-name "Wowlheim (fusion test)" --exe mangosd_merged.exe
  # serveur principal : d'abord --dry-run, puis les etapes une par une (voir --help)
  python -I bots/server/integrate_main.py --core C:\\Wowlheim\\src\\mangos-classic --run C:\\Wowlheim\\run --db-suffix "" --dry-run
"""
import argparse
import datetime
import glob
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import setup_run  # noqa: E402  (configs partagees avec le serveur de test)

MYSQL_BIN = r"C:\Program Files\MySQL\MySQL Server 8.4\bin"
VCPKG = r"C:\Wowlheim\bots\vcpkg_installed\x64-windows"   # boost (avec boost-bimap) + OpenSSL des bots
TEXT_SQL = ["ai_playerbot_texts_fr.sql", "ai_playerbot_texts_fr_extra.sql",
            "ai_playerbot_texts_casual.sql", "ai_playerbot_texts_human.sql"]
CACHES = ["ai_playerbot_equip_cache", "ai_playerbot_rnditem_cache", "ai_playerbot_rarity_cache",
          "ai_playerbot_item_info_cache", "ai_playerbot_tele_cache"]
STEPS = ["core", "module", "cmake", "sql", "conf", "deploy", "shortcut"]

DRY = False


class Fail(Exception):
    pass


def say(*a):
    print(*a, flush=True)


def run(cmd, cwd=None, check=True, inp=None, capture=True, write=True):
    """write=True : la commande modifie quelque chose (sautee en --dry-run)."""
    shown = " ".join('"%s"' % c if " " in c else c for c in cmd)
    if DRY and write:
        say("  [dry-run] " + shown + ("  < " + inp if inp else ""))
        return ""
    stdin = open(inp, "rb") if inp else None
    try:
        p = subprocess.run(cmd, cwd=cwd, stdin=stdin, capture_output=capture)
    finally:
        if stdin:
            stdin.close()
    out = (p.stdout or b"").decode("utf-8", "replace")
    if check and p.returncode:
        raise Fail("echec (%d) : %s\n%s%s" % (p.returncode, shown, out, (p.stderr or b"").decode("utf-8", "replace")))
    return out


# ---------------------------------------------------------------- module

def git(dest, *args, **kw):
    # --no-optional-locks : un « git status » de lecture ne reecrit pas l'index (arbre principal intouche en --dry-run)
    return run(["git", "--no-optional-locks", "-C", dest] + list(args), **kw)


def norm(b):
    return b.replace(b"\r\n", b"\n")


def compare_trees(a, b):
    """(identiques octet pour octet, identiques aux fins de ligne pres, differents, absents d'un cote)."""
    def files(root):
        out = set()
        for d, ds, fs in os.walk(root):
            ds[:] = [x for x in ds if x != ".git"]
            out |= {os.path.relpath(os.path.join(d, f), root) for f in fs}
        return out
    fa, fb = files(a), files(b)
    same = 0
    eol, diff = [], []
    for r in sorted(fa & fb):
        x = open(os.path.join(a, r), "rb").read()
        y = open(os.path.join(b, r), "rb").read()
        if x == y:
            same += 1
        elif norm(x) == norm(y):
            eol.append(r)
        else:
            diff.append(r)
    return same, eol, diff, sorted(fa ^ fb)


def step_core(a):
    """Arbre NEUF (essai) : clone de --core-src + server/core.patch + server/Wowlheim/*, relus a chaque execution.
    Arbre existant : recopie server/Wowlheim/* (comme tools/sync_server.ps1) et verifie l'etat de core.patch."""
    patch = os.path.join(REPO, "server", "core.patch")
    wl_src = os.path.join(REPO, "server", "Wowlheim")
    wl_dst = os.path.join(a.core, "src", "game", "Wowlheim")
    say("== core : %s" % a.core)
    if not os.path.isdir(a.core):
        run(["git", "clone", "--no-hardlinks", a.core_src, a.core])
        run(["git", "-C", a.core, "apply", "--whitespace=nowarn", patch])
        say("  clone de %s + %s" % (a.core_src, patch))
    else:
        if subprocess.run(["git", "-C", a.core, "apply", "--check", "--reverse", patch], capture_output=True).returncode == 0:
            say("  core.patch deja en place")
        elif subprocess.run(["git", "-C", a.core, "apply", "--check", patch], capture_output=True).returncode == 0:
            run(["git", "-C", a.core, "apply", "--whitespace=nowarn", patch])
            say("  core.patch applique")
        else:
            # cas normal du serveur principal : core.patch est EXPORTE de cet arbre (sync_server.ps1, accents des
            # commentaires perdus par Out-File -Encoding ascii) ; on ne touche pas au coeur
            say("  core.patch ni applicable ni detecte a l'envers : coeur laisse tel quel (arbre source du patch ?)")
    files = sorted(glob.glob(os.path.join(wl_src, "*")))
    say("  server/Wowlheim -> %s (%d fichiers)" % (wl_dst, len(files)))
    if not DRY:
        os.makedirs(wl_dst, exist_ok=True)
        for f in files:
            if os.path.isfile(f):
                shutil.copy2(f, wl_dst)


def step_module(a):
    dest = os.path.join(a.core, "src", "modules", "PlayerBots")
    patch = os.path.abspath(a.repo_patch)
    say("== module : %s" % dest)
    if not os.path.isdir(os.path.join(a.core, "src", "game")):
        raise Fail("--core n'est pas un arbre CMaNGOS : %s" % a.core)
    if not os.path.isdir(dest):
        run(["git", "clone", "--no-hardlinks", "--no-checkout", a.module_src, dest])
        git(dest, "checkout", "-q", a.module_commit)
        if DRY:
            say("  [dry-run] git apply %s" % patch)
            return
    head = git(dest, "rev-parse", "HEAD", write=False).strip()
    want = git(dest, "rev-parse", a.module_commit + "^{commit}", write=False).strip()
    if head != want:
        raise Fail("module au commit %s, attendu %s (%s) : a regler a la main" % (head[:10], a.module_commit, want[:10]))
    fwd = subprocess.run(["git", "-C", dest, "apply", "--check", patch], capture_output=True)
    if fwd.returncode == 0:
        if git(dest, "status", "--porcelain", write=False).strip():
            raise Fail("le module a des modifications locales qui ne viennent pas du patch")
        run(["git", "-C", dest, "apply", "--whitespace=nowarn", patch])
        if not DRY:
            say("  patch applique : %s" % patch)
    elif subprocess.run(["git", "-C", dest, "apply", "--check", "--reverse", patch], capture_output=True).returncode == 0:
        say("  patch deja applique (git apply --reverse --check OK) : rien a faire")
    elif a.reset_module:
        # patch mis a jour depuis la derniere integration : module remis au commit d'origine puis patch re-applique
        say("  ancien patch en place : --reset-module -> git checkout + git clean du module, puis nouveau patch")
        git(dest, "checkout", "-q", "--", ".")
        git(dest, "clean", "-fdq")
        run(["git", "-C", dest, "apply", "--whitespace=nowarn", patch])
        say("  patch applique : %s" % patch)
    else:
        raise Fail("le patch ne s'applique pas et n'est pas deja applique (patch mis a jour ? relancer avec "
                   "--reset-module) :\n" + "\n".join(fwd.stderr.decode("utf-8", "replace").splitlines()[:6]))
    if DRY or not a.reference:
        return
    if not os.path.isdir(a.reference):
        say("  (pas d'arbre de reference %s : comparaison sautee)" % a.reference)
        return
    same, eol, diff, alone = compare_trees(a.reference, dest)
    say("  comparaison avec %s : %d identiques, %d aux fins de ligne pres, %d differents, %d absents d'un cote"
        % (a.reference, same, len(eol), len(diff), len(alone)))
    for r in eol[:10]:
        say("    (fins de ligne seulement) " + r)
    for r in diff[:20] + alone[:20]:
        say("    ! " + r)
    if diff or alone:
        raise Fail("le module integre differe de l'arbre de reference")


# ---------------------------------------------------------------- cmake

def step_cmake(a):
    v = a.vcpkg.replace("\\", "/")
    core = a.core.replace("\\", "/")
    mysql_root = os.path.dirname(MYSQL_BIN).replace("\\", "/")
    say("== cmake (a lancer a la main ; rien n'est compile par ce script)")
    say("  # depuis Git Bash : MSYS_NO_PATHCONV=1 evite que /O2 devienne un chemin")
    say('  MSYS_NO_PATHCONV=1 cmake -S %s -B %s -G "Visual Studio 17 2022" -A x64 \\' % (core, a.build.replace("\\", "/")))
    say("    -DBUILD_PLAYERBOTS=ON -DFETCHCONTENT_SOURCE_DIR_PLAYERBOTS=%s/src/modules/PlayerBots \\" % core)
    say("    -DCMAKE_PREFIX_PATH=%s -DBoost_DIR=%s/share/boost -DOPENSSL_ROOT_DIR=%s \\" % (v, v, v))
    say('    -DMYSQL_ROOT_DIR="%s" -DMYSQL_INCLUDE_DIR="%s/include" -DMYSQL_LIBRARY="%s/lib/libmysql.lib" \\'
        % (mysql_root, mysql_root, mysql_root))
    say("    -DBUILD_EXTRACTORS=ON -DBUILD_SCRIPTDEV=ON -DBUILD_LOGIN_SERVER=ON -DBUILD_GAME_SERVER=ON -DPCH=ON \\")
    say('    -DCMAKE_INSTALL_PREFIX=%s -DCMAKE_CXX_FLAGS_RELEASE="/O2 /Ob2 /DNDEBUG" -DCMAKE_C_FLAGS_RELEASE="/O2 /Ob2 /DNDEBUG"'
        % a.run.replace("\\", "/"))
    say("  MSYS_NO_PATHCONV=1 cmake --build %s --config Release --target mangosd realmd --parallel 10 -- /p:CL_MPCount=4"
        % a.build.replace("\\", "/"))
    say("  # /p:CL_MPCount=4 : sans lui, MSBuild lance un cl.exe par coeur et le PCH de playerbots (~700 Mo chacun)")
    say("  # epuise la memoire (C1076 / C3859) quand LM Studio est charge.")
    say("  # Boost/OpenSSL : racine %s (boost-bimap requis par playerbots, absent de C:\\Wowlheim\\vcpkg)." % a.vcpkg)
    say("  # Le binaire depend alors des DLL de cette racine : l'etape deploy les copie dans <run>.")
    say("  # Utiliser un dossier de build NEUF (ex. C:\\Wowlheim\\build_pb) : un ancien cache garderait les chemins")
    say("  # OpenSSL de C:\\Wowlheim\\vcpkg (versions differentes de celles de la racine des bots).")


# ---------------------------------------------------------------- sql

def mysql(a, db, query=None, inp=None, write=True, force=False):
    cmd = [os.path.join(MYSQL_BIN, "mysql.exe"), "-uroot", "-h127.0.0.1", "--default-character-set=utf8mb4", "-N", "-B"]
    if force:
        cmd.append("--force")
    if db:
        cmd.append(db)
    if query:
        cmd += ["-e", query]
    return run(cmd, inp=inp, write=write, check=not force)


def tables(a, db):
    return set(mysql(a, None, "SELECT table_name FROM information_schema.tables WHERE table_schema='%s'" % db,
                     write=False).split())


def created_tables(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    return re.findall(r"CREATE TABLE(?: IF NOT EXISTS)?\s+`?(\w+)`?", txt, re.I)


def apply_indexes(a, db, path):
    have = set(mysql(a, None, "SELECT CONCAT(table_name,'.',index_name) FROM information_schema.statistics "
                              "WHERE table_schema='%s'" % db, write=False).split())
    for m in re.finditer(r"create index (\w+) on (\w+)\s*\(([^)]*)\)", open(path, encoding="utf-8").read(), re.I):
        idx, tbl, col = m.groups()
        if "%s.%s" % (tbl, idx) in have:
            say("    index %s.%s deja present" % (tbl, idx))
        else:
            mysql(a, db, "CREATE INDEX %s ON %s(%s)" % (idx, tbl, col))
            say("    index %s.%s cree" % (tbl, idx))


def dump(a, db, out, tables_=None):
    cmd = [os.path.join(MYSQL_BIN, "mysqldump.exe"), "-uroot", "-h127.0.0.1", "--default-character-set=utf8mb4",
           "--single-transaction", "--quick", "--routines", "--result-file=" + out, db] + (tables_ or [])
    run(cmd)


def step_sql(a):
    sfx = a.db_suffix
    world, chars, realm = "classicmangos" + sfx, "classiccharacters" + sfx, "classicrealmd" + sfx
    mod = os.path.join(a.core, "src", "modules", "PlayerBots", "sql")
    if not os.path.isdir(mod):
        raise Fail("SQL du module introuvables (%s) : etape module d'abord" % mod)
    say("== sql : monde %s, personnages %s, connexion %s" % (world, chars, realm))
    for db in (world, chars, realm, a.cache_src):
        if not mysql(a, None, "SELECT schema_name FROM information_schema.schemata WHERE schema_name='%s'" % db,
                     write=False).strip() and not DRY:
            raise Fail("base absente : %s" % db)
    if a.cache_src in (world, chars):
        raise Fail("--cache-src ne peut pas etre la base cible")
    # 1. sauvegardes AVANT toute modification
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(a.backup_dir, "playerbots%s_%s" % (sfx or "_main", stamp))
    if not DRY:
        os.makedirs(bdir, exist_ok=True)
    targets = [world, chars] + ([realm] if a.realm_port or a.realm_name else [])
    for db in targets:
        out = os.path.join(bdir, db + ".sql")
        say("  sauvegarde %s -> %s" % (db, out))
        dump(a, db, out)
        if not DRY and os.path.getsize(out) < 1000:
            raise Fail("sauvegarde suspecte (%d octets) : %s" % (os.path.getsize(out), out))
    # 1a. objets Valheim (>= 9 000 000, marteau de depart compris) retires aux bots aleatoires (comptes RNDBOT%) :
    #     inventaire, banque, equipement et courrier recu. bots/sql/remove_bot_valheim_items.sql (remplace
    #     remove_bot_hammer.sql, garde en repli si le nouveau fichier manque). Joueurs reels jamais touches.
    for name in ("remove_bot_valheim_items.sql", "remove_bot_hammer.sql"):
        hsql = os.path.join(REPO, "bots", "sql", name)
        if not os.path.exists(hsql):
            continue
        tmp_h = os.path.join(bdir, name)
        if not DRY:
            with open(hsql, encoding="utf-8") as f, open(tmp_h, "w", encoding="utf-8") as g:
                g.write(f.read().replace("__REALMD__", realm))
        out = mysql(a, chars, inp=tmp_h)
        say("  personnages <- bots/sql/%s (objets Valheim retires aux bots : %s)" % (name, " ".join(out.split()) or "-"))
        break
    # 1b. (option) SQL Valheim du depot, relus a chaque execution (scripts rejouables de server/sql)
    if a.valheim_sql:
        for sub, db in (("world", world), ("characters", chars)):
            for f in sorted(glob.glob(os.path.join(REPO, "server", "sql", sub, "*.sql"))):
                say("  %-10s <- server/sql/%s/%s" % ("monde" if sub == "world" else "personnages", sub, os.path.basename(f)))
                mysql(a, db, inp=f)
    # 2. tables du module, base monde (donnees statiques : DROP + CREATE, toujours rejouees ; index si absents)
    wfiles = sorted(glob.glob(os.path.join(mod, "world", "*.sql"))) + sorted(glob.glob(os.path.join(mod, "world", "classic", "*.sql")))
    for f in wfiles:
        say("  monde      <- %s" % os.path.relpath(f, mod))
        if os.path.basename(f) == "ai_playerbot_indexes.sql":
            apply_indexes(a, world, f)
        else:
            # --force : ai_playerbot_travel_nodes.sql (amont) contient une cle en double vers la ligne 368147 ;
            # sans --force mysql s'arrete la et l'integration aussi. Les lignes en double sont simplement ignorees.
            mysql(a, world, inp=f, force=True)
    # 3. textes FR / sobres de Wowlheim (apres ai_playerbot_texts.sql, dans cet ordre)
    for name in TEXT_SQL:
        f = os.path.join(REPO, "bots", "sql", name)
        say("  monde      <- bots/sql/%s" % name)
        mysql(a, world, inp=f)
    # 4. tables du module, base personnages : creees si absentes (donnees vivantes des bots conservees)
    have = tables(a, chars)
    for f in sorted(glob.glob(os.path.join(mod, "characters", "*.sql"))):
        made = created_tables(f)
        if made and all(t in have for t in made) and not a.force_chars:
            say("  personnages = %s (tables deja presentes : %s)" % (os.path.basename(f), ", ".join(made)))
            continue
        say("  personnages <- %s" % os.path.basename(f))
        mysql(a, chars, inp=f)
    # 5. caches calcules par playerbots, copies depuis la base du serveur de test
    tmp = os.path.join(bdir, "caches_%s.sql" % a.cache_src)
    say("  caches %s.{%s} -> %s" % (a.cache_src, ",".join(c[len("ai_playerbot_"):] for c in CACHES), chars))
    dump(a, a.cache_src, tmp, CACHES)
    mysql(a, chars, inp=tmp)
    # 6. realmlist
    if a.realm_port or a.realm_name:
        sets = []
        if a.realm_port:
            sets.append("port=%d" % a.realm_port)
        if a.realm_name:
            sets.append("name='%s'" % a.realm_name.replace("'", "''"))
        mysql(a, realm, "UPDATE realmlist SET %s WHERE id=%d" % (", ".join(sets), a.realm_id))
        say("  realmlist %s : %s" % (realm, ", ".join(sets)))
    if DRY:
        return
    # 7. controles
    for db, want in ((world, ["ai_playerbot_texts", "ai_playerbot_travelnode", "ai_playerbot_named_location"]),
                     (chars, CACHES + ["ai_playerbot_random_bots", "ai_playerbot_names"])):
        missing = [t for t in want if t not in tables(a, db)]
        if missing:
            raise Fail("tables absentes dans %s : %s" % (db, missing))
    q = ("SELECT COUNT(*), SUM(CRC32(CONCAT_WS('|', name, text, text_loc2, say_type, reply_type))) FROM ai_playerbot_texts")
    mine = mysql(a, world, q, write=False).split()
    say("  ai_playerbot_texts %s : %s lignes, somme de controle %s" % (world, mine[0], mine[1]))
    if a.compare_world:
        ref = mysql(a, a.compare_world, q, write=False).split()
        say("  ai_playerbot_texts %s : %s lignes, somme de controle %s -> %s" % (
            a.compare_world, ref[0], ref[1], "IDENTIQUE" if ref == mine else "DIFFERENT"))
    for c in CACHES:
        n_src = mysql(a, a.cache_src, "SELECT COUNT(*) FROM %s" % c, write=False).strip()
        n_dst = mysql(a, chars, "SELECT COUNT(*) FROM %s" % c, write=False).strip()
        say("  %-30s %s -> %s lignes%s" % (c, n_src, n_dst, "" if n_src == n_dst else "  !! ECART"))
    say("  sauvegardes : %s" % bdir)


# ---------------------------------------------------------------- conf

def read_conf(path):
    vals = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^\s*([A-Za-z0-9_.]+)\s*=\s*(.*?)\s*$", line)
        if m:
            vals[m.group(1)] = m.group(2)
    return vals


def with_suffix(value, sfx):
    """« "127.0.0.1;3306;mangos;mangos;classicmangos" » -> base suffixee (sans doubler un suffixe deja la)."""
    v = value.strip('"')
    parts = v.split(";")
    base = re.sub(r"(_bots|_m)$", "", parts[-1]) if sfx else parts[-1]
    if sfx:
        base = base + sfx if not base.endswith(sfx) else base
    parts[-1] = base
    return '"%s"' % ";".join(parts)


def edit_conf(path, overrides):
    if not overrides:
        say("  %s : rien a changer" % path)
        return
    for k, v in overrides.items():
        say("  %s : %s = %s" % (os.path.basename(path), k, v))
    if DRY:
        return
    bak = path + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, bak)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(setup_run.apply(text, overrides))
    say("  (copie de l'ancien fichier : %s)" % bak)


def logs_override(cur, run_dir):
    """LogsDir pointant hors de <run> (ex. config copiee du serveur principal) -> <run>/logs."""
    v = cur.get("LogsDir", "").strip('"')
    if v and os.path.isabs(v) and not os.path.abspath(v).lower().startswith(os.path.abspath(run_dir).lower()):
        return {"LogsDir": '"%s/logs"' % run_dir.replace("\\", "/")}
    return {}


def dist(a, name, src_rel):
    p = os.path.join(a.bin, name)
    if os.path.exists(p):
        return p
    p = os.path.join(a.core, *src_rel)
    if not os.path.exists(p):
        raise Fail("modele de config introuvable : %s (ni dans %s)" % (name, a.bin))
    return p


def step_conf(a):
    say("== conf : %s" % a.run)
    mconf, rconf = os.path.join(a.run, "mangosd.conf"), os.path.join(a.run, "realmd.conf")
    for p in (mconf, rconf):
        if not os.path.exists(p):
            raise Fail("%s absent : on part TOUJOURS de la config existante du run cible (reglages Valheim)" % p)
    cur = read_conf(mconf)
    over = {}
    for k in ("LoginDatabaseInfo", "WorldDatabaseInfo", "CharacterDatabaseInfo", "LogsDatabaseInfo"):
        nv = with_suffix(cur[k], a.db_suffix)
        if nv != cur[k]:
            over[k] = nv
    if a.world_port and cur.get("WorldServerPort") != str(a.world_port):
        over["WorldServerPort"] = str(a.world_port)
    over.update(logs_override(cur, a.run))
    edit_conf(mconf, over)
    cur = read_conf(rconf)
    over = {}
    nv = with_suffix(cur["LoginDatabaseInfo"], a.db_suffix)
    if nv != cur["LoginDatabaseInfo"]:
        over["LoginDatabaseInfo"] = nv
    if a.realm_port and cur.get("RealmServerPort") != str(a.realm_port):
        over["RealmServerPort"] = str(a.realm_port)
    over.update(logs_override(cur, a.run))
    edit_conf(rconf, over)
    pb = dist(a, "aiplayerbot.conf.dist", ("src", "modules", "PlayerBots", "playerbot", "aiplayerbot.conf.dist.in"))
    ac = dist(a, "anticheat.conf.dist", ("src", "game", "Anticheat", "module", "anticheat.conf.dist.in"))
    say("  aiplayerbot.conf (%d bots, %d comptes, LLM 127.0.0.1:%d) depuis %s" % (a.bots, a.accounts, a.bridge_port, pb))
    say("  anticheat.conf (Enable = 0) ; ahbot.conf (AhBot.Enabled = 0) dans %s et %s"
        % (a.run, os.path.join(os.path.dirname(os.path.abspath(a.run)), "etc")))
    if not DRY:
        os.makedirs(os.path.join(a.run, "logs"), exist_ok=True)
        setup_run.write_bot_confs(a.run, pb, ac, a.bots, a.accounts, a.bridge_port)


# ---------------------------------------------------------------- deploy / shortcut

def image_running(name):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % name, "/NH"], capture_output=True).stdout
    return name.lower().encode() in out.lower()


def step_deploy(a):
    exe = a.exe
    rexe = exe.replace("mangosd", "realmd")
    say("== deploy : %s -> %s (%s, %s)" % (a.bin, a.run, exe, rexe))
    for name in (exe, rexe):
        if image_running(name):
            if not DRY:
                raise Fail("%s tourne : arrete-le avant de copier" % name)
            say("  ATTENTION : %s tourne, il faudra l'arreter avant la copie" % name)
    if not os.path.exists(os.path.join(a.bin, "mangosd.exe")) and not DRY:
        raise Fail("mangosd.exe introuvable dans %s (compiler d'abord)" % a.bin)
    dlls = glob.glob(os.path.join(a.bin, "*.dll")) + glob.glob(os.path.join(a.vcpkg, "bin", "*.dll"))
    say("  %d DLL (build + %s)" % (len(dlls), os.path.join(a.vcpkg, "bin")))
    if DRY:
        return
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    for name in [exe, rexe] + [os.path.basename(f) for f in dlls]:   # anciens binaires / DLL gardes a cote
        old = os.path.join(a.run, name)
        if os.path.exists(old):
            os.makedirs(os.path.join(a.run, "avant_playerbots_" + stamp), exist_ok=True)
            shutil.copy2(old, os.path.join(a.run, "avant_playerbots_" + stamp, name))
    for f in dlls:
        shutil.copy2(f, a.run)
    for src, dst in (("mangosd", exe), ("realmd", rexe)):
        shutil.copy2(os.path.join(a.bin, src + ".exe"), os.path.join(a.run, dst))
        pdb = os.path.join(a.bin, src + ".pdb")
        if os.path.exists(pdb):
            shutil.copy2(pdb, os.path.join(a.run, os.path.splitext(dst)[0] + ".pdb"))
    say("  copie faite (anciens fichiers dans %s)" % os.path.join(a.run, "avant_playerbots_" + stamp))


LAUNCHER = r"""# Genere par bots/server/integrate_main.py : serveur Wowlheim + bots, puis pont LLM.
$ErrorActionPreference = 'Continue'
$repo = '{repo}'
$run = '{run}'
$Host.UI.RawUI.WindowTitle = '{title}'
if (-not (Get-Process mysqld -ErrorAction SilentlyContinue)) {{ Write-Host 'MySQL ne tourne pas' -ForegroundColor Red; Read-Host 'Entree'; exit 1 }}
if (Get-Process '{exe_base}' -ErrorAction SilentlyContinue) {{ Write-Host 'serveur deja en marche' }}
else {{
    Start-Process python -ArgumentList '-I', 'bots/server/run_server.py', '--run', $run, '--exe', '{exe}' -WorkingDirectory $repo -WindowStyle Minimized
    Write-Host 'serveur lance (fenetre reduite python)'
}}
$lms = Join-Path $env:USERPROFILE '.lmstudio\bin\lms.exe'
$model = 'google/gemma-4-12b-qat'
if (Test-Path $lms) {{
    $ps = & $lms ps 2>&1 | Out-String
    if ($ps -notmatch [regex]::Escape($model)) {{ & $lms unload --all 2>&1 | Out-Null; & $lms load $model -y --context-length 8192 2>&1 | Select-Object -Last 1 }}
}}
try {{ Invoke-RestMethod http://127.0.0.1:{port}/health -TimeoutSec 2 | Out-Null; Write-Host 'pont LLM deja en marche (verifier ses bases : --char-db {chars} --world-db {world})' }}
catch {{
    Start-Process python -ArgumentList '-I', 'bots/llm_bridge/bridge.py', '--port', '{port}', '--char-db', '{chars}', '--world-db', '{world}' -WorkingDirectory $repo -WindowStyle Minimized
    Write-Host 'pont LLM lance'
}}
$out = Join-Path $run 'mangosd.out'
for ($i = 0; $i -lt 600; $i += 5) {{
    if ((Test-Path $out) -and (Select-String -Path $out -Pattern 'World initialized' -Quiet)) {{ Write-Host 'monde pret'; break }}
    Start-Sleep -Seconds 5; Write-Host -NoNewline '.'
}}
Start-Sleep -Seconds 5
"""


def step_shortcut(a):
    ps1 = os.path.join(a.run, "lancer_wowlheim_bots.ps1")
    say("== shortcut : %s" % ps1)
    body = LAUNCHER.format(repo=REPO, run=a.run, title=a.shortcut, exe=a.exe, exe_base=os.path.splitext(a.exe)[0],
                           port=a.bridge_port, chars="classiccharacters" + a.db_suffix, world="classicmangos" + a.db_suffix)
    lnk = os.path.join(a.shortcut_dir, a.shortcut + ".lnk")
    say("  raccourci : %s" % lnk)
    if DRY:
        return
    with open(ps1, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(body)
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s'); $s.TargetPath = 'powershell.exe'; "
          "$s.Arguments = '-NoProfile -ExecutionPolicy Bypass -File \"%s\"'; $s.WorkingDirectory = '%s'; $s.Save()"
          % (lnk.replace("'", "''"), ps1, REPO))
    run(["powershell", "-NoProfile", "-Command", ps])


# ---------------------------------------------------------------- main

def main(argv=None):
    global DRY
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--core", required=True, help="arbre CMaNGOS-classic (avec Wowlheim)")
    ap.add_argument("--module-src", default=r"C:\Wowlheim\src\playerbots", help="clone playerbots a cloner")
    ap.add_argument("--module-commit", default="c6288bf")
    ap.add_argument("--repo-patch", default=os.path.join(REPO, "bots", "playerbots.patch"))
    ap.add_argument("--reference", default=r"C:\Wowlheim\bots\src\mangos-classic\src\modules\PlayerBots",
                    help="module du serveur de test, compare fichier par fichier ('' pour sauter)")
    ap.add_argument("--build", help=r"dossier de build (defaut : <core>\..\..\build_pb)")
    ap.add_argument("--bin", help=r"sortie du build (defaut : <build>\bin\x64_Release)")
    ap.add_argument("--vcpkg", default=VCPKG)
    ap.add_argument("--run", required=True, help="dossier d'execution cible")
    ap.add_argument("--db-suffix", required=True, help="'' pour le principal, '_m' pour l'essai")
    ap.add_argument("--bots", type=int, default=100)
    ap.add_argument("--accounts", type=int, default=20)
    ap.add_argument("--bridge-port", type=int, default=5005)
    ap.add_argument("--world-port", type=int, help="WorldServerPort (essai : 8086) ; absent = inchange")
    ap.add_argument("--realm-port", type=int, help="RealmServerPort + realmlist.port (essai : 3725) ; absent = inchange")
    ap.add_argument("--realm-name", help="realmlist.name (absent = inchange)")
    ap.add_argument("--realm-id", type=int, default=1)
    ap.add_argument("--cache-src", default="classiccharacters_bots", help="base d'ou copier les caches playerbots")
    ap.add_argument("--compare-world", default="classicmangos_bots", help="base monde de reference pour les textes ('' = non)")
    ap.add_argument("--core-src", default=r"C:\Wowlheim\src\mangos-classic", help="etape core : coeur a cloner (lecture seule)")
    ap.add_argument("--reset-module", action="store_true", help="patch mis a jour : remet le module au commit puis re-applique")
    ap.add_argument("--valheim-sql", action="store_true",
                    help="etape sql : rejoue aussi server/sql/world et server/sql/characters du depot (essai)")
    ap.add_argument("--force-chars", action="store_true", help="rejoue aussi les SQL personnages deja presents (remet a zero les bots)")
    ap.add_argument("--backup-dir", help=r"defaut : <run>\..\backup")
    ap.add_argument("--exe", default="mangosd.exe", help="nom du binaire du monde dans <run> (essai : mangosd_merged.exe)")
    ap.add_argument("--shortcut", default="Wowlheim - serveur et bots", help="nom du raccourci")
    ap.add_argument("--shortcut-dir", default=os.path.join(os.path.expanduser("~"), "Desktop"))
    ap.add_argument("--steps", default="module,cmake,sql,conf", help="parmi " + ",".join(STEPS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    DRY = a.dry_run
    a.core = os.path.abspath(a.core)
    a.run = os.path.abspath(a.run)
    a.build = os.path.abspath(a.build or os.path.join(os.path.dirname(os.path.dirname(a.core)), "build_pb"))
    a.bin = a.bin or os.path.join(a.build, "bin", "x64_Release")
    a.backup_dir = a.backup_dir or os.path.join(os.path.dirname(a.run), "backup")
    if a.db_suffix and not re.fullmatch(r"_\w+", a.db_suffix):
        raise SystemExit("--db-suffix : '' ou _xxx")
    steps = [s.strip() for s in a.steps.split(",") if s.strip()]
    bad = [s for s in steps if s not in STEPS]
    if bad:
        raise SystemExit("etapes inconnues : %s" % bad)
    say("integrate_main : core=%s run=%s suffixe=%r etapes=%s%s" % (a.core, a.run, a.db_suffix, ",".join(steps),
                                                                    "  (DRY-RUN)" if DRY else ""))
    funcs = {"core": step_core, "module": step_module, "cmake": step_cmake, "sql": step_sql, "conf": step_conf,
             "deploy": step_deploy, "shortcut": step_shortcut}
    try:
        for s in STEPS:
            if s in steps:
                funcs[s](a)
    except Fail as e:
        say("ERREUR : %s" % e)
        return 1
    say("termine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
