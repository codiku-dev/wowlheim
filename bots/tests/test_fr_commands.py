"""Wowlheim : test hors jeu de la traduction des ordres francais des bots (playerbots).

Compile le vrai en-tete C++ du module (WowlheimFrenchCommands.h) avec MSVC (cl.exe via vcvars64.bat)
dans un dossier temporaire, puis verifie la table et une liste de phrases.

    python -I bots/tests/test_fr_commands.py
    python -I bots/tests/test_fr_commands.py --header C:\\chemin\\WowlheimFrenchCommands.h
"""
import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HEADER = r"C:\Wowlheim\bots\src\mangos-classic\src\modules\PlayerBots\playerbot\WowlheimFrenchCommands.h"
VCVARS = [
    r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
]

BOT = "Gengeanvi"

# (message tape par le joueur, commande attendue ; "" = aucune commande)
CASES = [
    # suivre
    ("suis-moi", "follow"), ("Suis moi !", "follow"), ("suis-moi stp", "follow"), ("Gengeanvi, suis-moi", "follow"),
    ("suis moi Gengeanvi", "follow"), ("viens avec moi", "follow"), ("on y va", "follow"), ("On y va ?", "follow"),
    ("allez on y va", "follow"), ("go", "follow"), ("GO GO", "follow"), ("let's go", "follow"), ("viens", "follow"),
    ("viens ici", "follow"), ("allez viens", "follow"), ("on y va go", "follow"), ("en route !", "follow"),
    ("suivez-moi les gars", "follow"),
    # rester / arreter
    ("reste là", "stay"), ("reste la", "stay"), ("RESTE ICI", "stay"), ("attends", "stay"), ("attends-moi ici", "stay"),
    ("attends moi la stp", "stay"), ("bouge pas", "stay"), ("ne bouge pas !", "stay"), ("stop", "stay"),
    ("arrête", "stay"), ("arrête-toi", "stay"), ("ARRÊTEZ", "stay"),
    # attaquer
    ("attaque", "attack"), ("attaque-le", "attack"), ("attaque le !", "attack"), ("tape-le", "attack"),
    ("tapez la", "attack"), ("go attaque", "attack"), ("à l'attaque", "attack"), ("on attaque", "attack"),
    ("tue-le", "attack"), ("pull", "pull"), ("pull le", "pull"),
    # rejoindre de loin
    ("rejoins-moi", "follow"), ("rejoins moi stp", "follow"), ("viens me rejoindre", "follow"), ("tp toi", "follow"),
    ("téléporte-toi", "follow"),
    # ramasser
    ("loot", "loot"), ("ramasse", "loot"), ("ramasse le loot", "loot"), ("ramasse tout stp", "loot"),
    # esprit
    ("relâche ton esprit", "release"), ("relache", "release"), ("libère ton esprit", "release"),
    ("ressuscite-toi", "revive"), ("rez toi", "revive"),
    # groupe
    ("quitte le groupe", "leave"), ("quitte le groupe stp", "leave"), ("sors du groupe", "leave"),
    ("invite-moi", "invite"), ("inv", "invite"), ("inv stp", "invite"), ("tu peux m'inviter ?", "invite"),
    ("tu peux m’inviter ?", "invite"), ("Tu peux m'inviter s'il te plait ?", "invite"), ("invite moi stp", "invite"),
    ("peux-tu m'inviter", "invite"), ("tu m'inv ?", "invite"),
    # encodage latin-1 (octets isoles) au cas ou le client n'envoie pas d'UTF-8
    (b"arr\xeate".decode("latin-1"), "stay"),
    # pas des ordres : conversation, phrases longues, liens
    ("je te suis reconnaissant", ""), ("attends je reviens", ""), ("je suis la", ""), ("on y va quand tu veux pour les mortemines", ""),
    ("salut ça va ?", ""), ("tu fais quoi", ""), ("reste là je vais chercher a boire et je reviens dans 5 min", ""),
    ("ok", ""), ("stp", ""), ("merci", ""), ("", ""), ("suis-moi |cff1eff00|Hitem:1234|h[Epee]|h|r", ""),
    ("il faut qu'on y va", ""), ("je vais attaquer le boss", ""), ("le loot est nul", ""), ("Gengeanvi", ""),
    ("inventaire", ""), ("quitte", ""), ("viens on va faire une quete ensemble", ""),
]


def find_vcvars():
    for path in VCVARS:
        if os.path.isfile(path):
            return path
    return None


def build(header, outdir):
    vcvars = find_vcvars()
    if not vcvars:
        sys.exit("vcvars64.bat introuvable (Visual Studio 2022)")
    exe = os.path.join(outdir, "fr_commands_test.exe")
    src = os.path.join(HERE, "fr_commands_main.cpp")
    bat = os.path.join(outdir, "build.bat")
    with open(bat, "w", encoding="ascii") as f:
        f.write('@echo off\r\ncall "{}" >nul\r\ncl /nologo /EHsc /W4 /WX /std:c++17 /I"{}" "{}" /Fe"{}"\r\n'.format(
            vcvars, os.path.dirname(header), src, exe))
    res = subprocess.run(["cmd", "/d", "/c", bat], cwd=outdir, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr)
        sys.exit("echec de compilation")
    return exe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--header", default=DEFAULT_HEADER)
    args = parser.parse_args()

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        exe = build(os.path.abspath(args.header), tmp)

        # 1. la table et les mots de politesse sont deja normalises, sans doublon
        out = subprocess.run([exe, "--table"], capture_output=True, check=True).stdout.decode("ascii")
        seen = set()
        for line in out.splitlines():
            phrase, normalized, command = line.split("\t")
            if phrase != normalized:
                print("TABLE non normalisee : %r -> %r" % (phrase, normalized))
                failures += 1
            key = (phrase, command == "-")  # « go » est a la fois une phrase et un mot de politesse : voulu
            if key in seen:
                print("TABLE doublon : %r" % phrase)
                failures += 1
            seen.add(key)

        # 2. les cas
        payload = "".join("%s\t%s\n" % (BOT, msg) for msg, _ in CASES).encode("utf-8")
        # le cas latin-1 doit arriver en octets latin-1, pas en UTF-8
        latin = b"arr\xeate"
        payload = payload.replace(latin.decode("latin-1").encode("utf-8"), latin)
        out = subprocess.run([exe], input=payload, capture_output=True, check=True).stdout.decode("ascii")
        got = out.replace("\r", "").split("\n")[:len(CASES)]
        for (msg, expected), result in zip(CASES, got):
            if result != expected:
                print("ECHEC %r : attendu %r, obtenu %r" % (msg, expected, result))
                failures += 1

    total = len(CASES) + 1
    print("%d cas, %d echec(s)" % (total, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
