#!/usr/bin/env python3
"""Banc rapide de modeles LM Studio pour le chat des bots : UN modele charge a la fois.

Pour chaque modele : tout decharger, charger le modele seul, rejouer un sous-ensemble de
eval_chat.py (salut, questions perso, memoire, casser le personnage, lore), noter latence et
reponses vides, puis decharger. A la fin, recharge le modele de service (--final).

  python -I bots/tests/bench_models.py MODELE [MODELE ...] [--final google/gemma-4-12b-qat]
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LMS = os.path.join(os.environ["USERPROFILE"], ".lmstudio", "bin", "lms.exe")
SCENARIOS = "S01,S05,S06,S07,S12"
OUT = r"C:\Wowlheim\bots\state\eval"


def lms(*args, timeout=600):
    r = subprocess.run([LMS, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout)
    return (r.stdout + r.stderr).strip()


def free_ram_gb():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
                         capture_output=True, text=True).stdout.strip()
    return int(out) / 1024 / 1024 if out.isdigit() else -1


def vram_used_mb():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.strip()
    return int(out) if out.isdigit() else -1


def bench(model):
    print("\n=== %s ===" % model, flush=True)
    print(lms("unload", "--all"))
    t0 = time.time()
    print(lms("load", model, "-y", "--context-length", "4096"))
    load_s = time.time() - t0
    print(lms("ps"))
    info = {"model": model, "chargement_s": round(load_s, 1), "vram_mo": vram_used_mb(), "ram_libre_go": round(free_ram_gb(), 1)}
    tag = "bench"
    t1 = time.time()
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "eval_chat.py"), "--model", model, "--tag", tag,
                        "--only", SCENARIOS, "--extra", json.dumps({"reasoning_effort": "none"})],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    info["banc_s"] = round(time.time() - t1, 1)
    path = os.path.join(OUT, "%s_%s.json" % (model.replace("/", "_"), tag))
    try:
        with open(path, encoding="utf-8") as f:
            info["resume"] = json.load(f).get("summary")
        info["fichier"] = path
    except OSError:
        info["erreur"] = (r.stdout + r.stderr)[-800:]
    print(json.dumps(info, ensure_ascii=False), flush=True)
    print(lms("unload", "--all"))
    return info


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # -I ignore PYTHONIOENCODING ; lms affiche des spinners
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--final", default="google/gemma-4-12b-qat")
    a = ap.parse_args()
    res = [bench(m) for m in a.models]
    if a.final:
        print(lms("load", a.final, "-y"))
        print(lms("ps"))
    with open(os.path.join(OUT, "bench_%s.json" % time.strftime("%H%M%S")), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
