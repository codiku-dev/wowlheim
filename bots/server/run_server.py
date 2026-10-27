#!/usr/bin/env python3
"""Lance le serveur de TEST des bots (realmd 3725 + mangosd 8086) depuis C:\\Wowlheim\\bots\\run.

Binaires renommes *_bots.exe pour ne pas etre tues par « taskkill /IM mangosd.exe ».
mangosd exige un stdin ouvert : on le tient par un tube. Pour envoyer une commande de
console, ajouter une ligne dans C:\\Wowlheim\\bots\\run\\console.in (elle est consommee).
Creer C:\\Wowlheim\\bots\\run\\stop pour un arret propre (« server shutdown 1 »).

  python -I bots/server/run_server.py
  python -I bots/server/run_server.py --run C:\\Wowlheim\\bots\\run_merged --exe mangosd_merged.exe  # autre dossier
"""
import argparse
import os
import subprocess
import sys
import time

RUN = r"C:\Wowlheim\bots\run"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=RUN, help="dossier d'execution (configs, DLL, binaires)")
    ap.add_argument("--exe", default="mangosd_bots.exe", help="binaire du monde, dans --run")
    ap.add_argument("--realmd-exe", help="binaire de connexion (defaut : --exe ou mangosd devient realmd)")
    a = ap.parse_args(argv)
    run = a.run
    realmd_exe = a.realmd_exe or a.exe.replace("mangosd", "realmd")
    CONSOLE = os.path.join(run, "console.in")
    STOP = os.path.join(run, "stop")
    for f in (CONSOLE, STOP):
        if os.path.exists(f):
            os.remove(f)
    realm = subprocess.Popen([os.path.join(run, realmd_exe), "-c", "realmd.conf"], cwd=run,
                             stdin=subprocess.DEVNULL,
                             stdout=open(os.path.join(run, "realmd.out"), "ab"),
                             stderr=open(os.path.join(run, "realmd.err"), "ab"))
    world = subprocess.Popen([os.path.join(run, a.exe), "-c", "mangosd.conf"], cwd=run,
                             stdin=subprocess.PIPE,
                             stdout=open(os.path.join(run, "mangosd.out"), "ab"),
                             stderr=open(os.path.join(run, "mangosd.err"), "ab"))
    print("realmd pid %d, mangosd pid %d" % (realm.pid, world.pid), flush=True)
    try:
        while world.poll() is None:
            if os.path.exists(STOP):
                os.remove(STOP)
                world.stdin.write(b"server shutdown 1\n")
                world.stdin.flush()
            if os.path.exists(CONSOLE):
                try:
                    with open(CONSOLE, "rb") as f:
                        data = f.read()
                    os.remove(CONSOLE)
                    world.stdin.write(data if data.endswith(b"\n") else data + b"\n")
                    world.stdin.flush()
                except OSError:
                    pass
            time.sleep(0.5)
    finally:
        if world.poll() is None:
            world.kill()
        realm.terminate()
    print("mangosd termine, code %s" % world.returncode, flush=True)
    return world.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
