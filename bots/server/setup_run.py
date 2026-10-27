#!/usr/bin/env python3
"""Prepare le serveur de TEST des bots dans C:\\Wowlheim\\bots\\run.

Copie les binaires compiles avec playerbots (C:\\Wowlheim\\bots\\build), les DLL de la
racine vcpkg separee, et ecrit les configs a partir des .dist + surcharges ci-dessous.
Ne touche ni a C:\\Wowlheim\\run ni aux bases principales : ports 3725/8086, bases *_bots.

  python -I bots/server/setup_run.py [--bots 5] [--accounts 5]
"""
import argparse
import glob
import os
import re
import shutil
import sys

ROOT = r"C:\Wowlheim\bots"
BIN = os.path.join(ROOT, "build", "bin", "x64_Release")
VCPKG_BIN = os.path.join(ROOT, "vcpkg_installed", "x64-windows", "bin")
RUN = os.path.join(ROOT, "run")
DB = "127.0.0.1;3306;mangos;mangos;"

MANGOSD = {
    "DataDir": '"C:/Wowlheim/data"',
    "LogsDir": '"C:/Wowlheim/bots/run/logs"',
    "LoginDatabaseInfo": '"%sclassicrealmd_bots"' % DB,
    "WorldDatabaseInfo": '"%sclassicmangos_bots"' % DB,
    "CharacterDatabaseInfo": '"%sclassiccharacters_bots"' % DB,
    "LogsDatabaseInfo": '"%sclassiclogs_bots"' % DB,
    "WorldServerPort": "8086",
    "BindIP": '"127.0.0.1"',
    "Ra.Enable": "0",
    "SOAP.Enabled": "0",
    "mmap.enabled": "1",
    "LogFileLevel": "2",  # traces « Wowlheim: » (sLog.outDetail) dans logs/Server.log
}

REALMD = {
    "LogsDir": '"C:/Wowlheim/bots/run/logs"',
    "LoginDatabaseInfo": '"%sclassicrealmd_bots"' % DB,
    "RealmServerPort": "3725",
    "BindIP": '"127.0.0.1"',
}

# Champs envoyes au pont LLM (bots/llm_bridge/bridge.py). Les <...> sont remplaces par
# playerbots (deja echappes pour JSON). Le pont repond au format KoboldCPP.
LLM_JSON = ('{"bot": "<bot name>", "bot_race": "<bot race>", "bot_class": "<bot class>", '
            '"bot_level": "<bot level>", "bot_gender": "<bot gender>", "zone": "<bot zone>", '
            '"subzone": "<bot subzone>", "other": "<other name>", "other_race": "<other race>", '
            '"other_class": "<other class>", "other_level": "<other level>", '
            '"channel": "<channel name>", "message": "<initial message>"}')


def playerbot_overrides(bots, accounts, bridge_port, silence_min=240, silence_max=480):
    return {
        "AiPlayerbot.Enabled": "1",
        "AiPlayerbot.RandomBotAutologin": "1",
        "AiPlayerbot.RandomBotLoginAtStartup": "1",
        "AiPlayerbot.MinRandomBots": str(bots),
        "AiPlayerbot.MaxRandomBots": str(bots),
        "AiPlayerbot.RandomBotAccountCount": str(accounts),
        "AiPlayerbot.RandomBotMaps": "0,1",
        "AiPlayerbot.RandomBotAutoJoinBG": "0",
        # Tous les bots actifs (sinon ~10 % seulement jouent et lisent le chat ; un chuchotement a un
        # bot inactif restait sans reponse). Cout CPU a mesurer : 45 bots vises.
        "AiPlayerbot.DisableActivityPriorities": "1",
        # Peupler la ou joue Robin (retour : « je croise personne ») : niveaux des bots calés sur ceux des
        # joueurs reels (jusqu'a +8), aucun bot tire d'office au niveau max, et les bots du bon niveau vont
        # jouer dans les zones ou il y a des joueurs reels (max 4 bots a moins de 120 m du point d'arrivee).
        "AiPlayerbot.SyncLevelWithPlayers": "1",
        "AiPlayerbot.SyncLevelMaxAbove": "8",
        "AiPlayerbot.RandomBotMaxLevelChance": "0",
        "AiPlayerbot.RandomBotTeleportNearPlayer": "1",
        "AiPlayerbot.RandomBotTeleportNearPlayerMaxAmount": "4",
        "AiPlayerbot.RandomBotTeleportNearPlayerMaxAmountRadius": "120",
        "AiPlayerbot.ForceActiveWhenNearPlayer": "1",
        "AiPlayerbot.botActiveAlone": "100",
        # Un bot de groupe ne prend pas seul le portail d'une instance : le joueur (meme non MJ)
        # lui chuchote « summon » (equivalent de la pierre de rencontre).
        "AiPlayerbot.NonGmFreeSummon": "0",   # retour Robin : jamais de bot qui se teleporte sur lui
        # Chat LLM : strategie « ai chat » (hors combat) active par defaut pour tous les bots.
        "AiPlayerbot.LLMEnabled": "2",
        "AiPlayerbot.LLMApiEndpoint": "http://127.0.0.1:%d/api/v1/generate" % bridge_port,
        "AiPlayerbot.LLMApiKey": "",
        "AiPlayerbot.LLMApiJson": LLM_JSON,
        "AiPlayerbot.LLMContextLength": "2000",
        "AiPlayerbot.LLMGenerationTimeout": "30",
        "AiPlayerbot.LLMMaxSimultaniousGenerations": "8",
        "AiPlayerbot.LLMResponseStartPattern": '("text":\\s*")',
        "AiPlayerbot.LLMResponseEndPattern": '(")',
        "AiPlayerbot.LLMResponseDeletePattern": "(\\\\n)",
        "AiPlayerbot.LLMResponseSplitPattern": "(.+)",
        "AiPlayerbot.LLMBotToBotChatChance": "0",
        "AiPlayerbot.LLMRpgAIChatChance": "0",
        "AiPlayerbot.LLMBlockedReplyChannels": "emote,temote",
        # Wowlheim : en groupe avec un vrai joueur, un bot parle parfois de lui-meme en /groupe (route
        # /spontaneous du pont) : silence de N s (N tire par bot entre Min et Max), niveau, mort, elite tue,
        # nouvelle zone, donjon. Les recharges (4 min par bot, 30 s en tout) sont dans le pont.
        "AiPlayerbot.WowlheimSpontaneousChat": "1",
        "AiPlayerbot.WowlheimNoCannedChat": "1",  # Robin : aucun texte predefini de playerbots, seulement le LLM
        "AiPlayerbot.WowlheimSpontaneousSilenceMin": str(silence_min),
        "AiPlayerbot.WowlheimSpontaneousSilenceMax": str(silence_max),
        # --- Retour Robin : plus AUCUN texte predefini de playerbots dit a voix haute (« Je viens de looter
        # du bois dur Elwyn » en General, « mes poches sont vides, faut les remplir », « jamais un humain
        # ferait ca »). Les bots ne parlent plus que par le LLM (pont) : reponses quand on leur parle et
        # initiatives /groupe ci-dessus. Ce que la config ne coupe pas (C++) est liste dans le rapport.
        # Annonces : EnableBroadcasts reste a 1 expres (a 0, playerbots tire urand(1, 0), comportement
        # indefini) ; chaque annonce et chaque canal est mis a 0, ce qui les coupe de facon certaine.
        "AiPlayerbot.EnableBroadcasts": "1",
        "AiPlayerbot.BroadcastToGuildGlobalChance": "0",
        "AiPlayerbot.BroadcastToWorldGlobalChance": "0",
        "AiPlayerbot.BroadcastToGeneralGlobalChance": "0",
        "AiPlayerbot.BroadcastToTradeGlobalChance": "0",
        "AiPlayerbot.BroadcastToLFGGlobalChance": "0",
        "AiPlayerbot.BroadcastToLocalDefenseGlobalChance": "0",
        "AiPlayerbot.BroadcastToWorldDefenseGlobalChance": "0",
        "AiPlayerbot.BroadcastToGuildRecruitmentGlobalChance": "0",
        "AiPlayerbot.BroadcastToSayGlobalChance": "0",
        "AiPlayerbot.BroadcastToYellGlobalChance": "0",
        # Retour Robin : butin, quetes, victimes, niveaux annonces dans les canaux = coupe.
        "AiPlayerbot.BroadcastChanceLootingItemPoor": "0",
        "AiPlayerbot.BroadcastChanceLootingItemNormal": "0",
        "AiPlayerbot.BroadcastChanceLootingItemUncommon": "0",
        "AiPlayerbot.BroadcastChanceLootingItemRare": "0",
        "AiPlayerbot.BroadcastChanceLootingItemEpic": "0",
        "AiPlayerbot.BroadcastChanceLootingItemLegendary": "0",
        "AiPlayerbot.BroadcastChanceLootingItemArtifact": "0",
        "AiPlayerbot.BroadcastChanceQuestAccepted": "0",
        "AiPlayerbot.BroadcastChanceQuestUpdateObjectiveCompleted": "0",
        "AiPlayerbot.BroadcastChanceQuestUpdateObjectiveProgress": "0",
        "AiPlayerbot.BroadcastChanceQuestUpdateFailedTimer": "0",
        "AiPlayerbot.BroadcastChanceQuestUpdateComplete": "0",
        "AiPlayerbot.BroadcastChanceQuestTurnedIn": "0",
        "AiPlayerbot.BroadcastChanceKillNormal": "0",
        "AiPlayerbot.BroadcastChanceKillElite": "0",
        "AiPlayerbot.BroadcastChanceKillRareelite": "0",
        "AiPlayerbot.BroadcastChanceKillWorldboss": "0",
        "AiPlayerbot.BroadcastChanceKillRare": "0",
        "AiPlayerbot.BroadcastChanceKillUnknown": "0",
        "AiPlayerbot.BroadcastChanceKillPet": "0",
        "AiPlayerbot.BroadcastChanceKillPlayer": "0",
        "AiPlayerbot.BroadcastChanceLevelupGeneric": "0",
        "AiPlayerbot.BroadcastChanceLevelupTenX": "0",
        "AiPlayerbot.BroadcastChanceLevelupMaxLevel": "0",
        "AiPlayerbot.BroadcastChanceGuildManagement": "0",
        # Retour Robin : suggestions de canal predefinies (donjons en anglais et hors niveau, « mes poches
        # sont vides », reputation, toxique, Lame-tonnerre) = coupe.
        "AiPlayerbot.BroadcastChanceSuggestInstance": "0",
        "AiPlayerbot.BroadcastChanceSuggestQuest": "0",
        "AiPlayerbot.BroadcastChanceSuggestGrindMaterials": "0",
        "AiPlayerbot.BroadcastChanceSuggestGrindReputation": "0",
        "AiPlayerbot.BroadcastChanceSuggestSell": "0",
        "AiPlayerbot.BroadcastChanceSuggestSomething": "0",
        "AiPlayerbot.BroadcastChanceSuggestSomethingToxic": "0",
        "AiPlayerbot.BroadcastChanceSuggestToxicLinks": "0",
        "AiPlayerbot.BroadcastChanceSuggestThunderfury": "0",
        # Retour Robin : reponses toutes faites aux messages de canal. Les chances a 0 ne suffisent pas
        # (ChatReplyDo les appelle quand meme) : prefixe introuvable pour les « liens toxiques ».
        "AiPlayerbot.ToxicLinksRepliesChance": "0",
        "AiPlayerbot.ThunderfuryRepliesChance": "0",
        "AiPlayerbot.ToxicLinksPrefix": "wowlheimsanstoxique",
        # Retour Robin : pas de /salut automatique a chaque joueur croise.
        "AiPlayerbot.EnableGreet": "0",
        # Retour Robin : pas d'invitation de groupe / guilde / charte non sollicitee aux vrais joueurs,
        # et pas de « tu veux rejoindre mon groupe ? » en /dire entre bots.
        "AiPlayerbot.RandomBotInvitePlayer": "0",
        "AiPlayerbot.InviteChat": "0",
        "AiPlayerbot.RandomBotSayWithoutMaster": "0",
        # Retour Robin : strategie « custom::say » (table classiccharacters_bots.ai_playerbot_custom_strategy)
        # = repliques /dire au butin (« Mes poches sont vides, faut les remplir »), vie basse, mana, AoE,
        # provocations. Strategie « emote » = suggestions de canal, /salut, emotes et « parle a » au hasard,
        # repliques anglaises aux emotes (« Hey there! »). On retire les deux des bots aleatoires.
        "AiPlayerbot.RandomBotCombatStrategies": "-threat,-custom::say",
        "AiPlayerbot.RandomBotNonCombatStrategies": "-custom::say,-emote",
    }


def apply(text, overrides):
    """Remplace « Cle = ... » (decommente si besoin) ; ajoute en fin les cles absentes."""
    done = set()
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*#?\s*([A-Za-z0-9_.]+)\s*=", line)
        if m and m.group(1) in overrides and m.group(1) not in done:
            k = m.group(1)
            out.append("%s = %s" % (k, overrides[k]))
            done.add(k)
        elif m and m.group(1) in overrides and not line.lstrip().startswith("#"):
            out.append("# (doublon neutralise) " + line)
        else:
            out.append(line)
    missing = [k for k in overrides if k not in done]
    if missing:
        out.append("")
        out.append("# --- Ajouts Wowlheim (bots/server/setup_run.py) ---")
        out += ["%s = %s" % (k, overrides[k]) for k in missing]
    return "\n".join(out) + "\n"


def write_conf(dist, dest, overrides):
    with open(dist, encoding="utf-8", errors="replace") as f:
        text = f.read()
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(apply(text, overrides))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", type=int, default=5)
    ap.add_argument("--accounts", type=int, default=5)
    ap.add_argument("--bridge-port", type=int, default=5005)
    ap.add_argument("--silence", type=int, nargs=2, default=(240, 480), metavar=("MIN", "MAX"),
                    help="silence de groupe (s) avant une phrase d'initiative ; ex. 40 60 pour un test")
    a = ap.parse_args(argv)
    if not os.path.exists(os.path.join(BIN, "mangosd.exe")):
        print("mangosd.exe introuvable dans", BIN, file=sys.stderr)
        return 1
    os.makedirs(os.path.join(RUN, "logs"), exist_ok=True)
    for f in glob.glob(os.path.join(BIN, "*.dll")) + glob.glob(os.path.join(VCPKG_BIN, "*.dll")):
        shutil.copy2(f, RUN)
    # Noms d'image distincts : l'autre session fait « taskkill /IM mangosd.exe » (tools/run_all.py).
    for exe in ("mangosd", "realmd"):
        shutil.copy2(os.path.join(BIN, exe + ".exe"), os.path.join(RUN, exe + "_bots.exe"))
        if os.path.exists(os.path.join(BIN, exe + ".pdb")):   # symboles pour les rapports de plantage
            shutil.copy2(os.path.join(BIN, exe + ".pdb"), RUN)
    write_conf(os.path.join(BIN, "mangosd.conf.dist"), os.path.join(RUN, "mangosd.conf"), MANGOSD)
    write_conf(os.path.join(BIN, "realmd.conf.dist"), os.path.join(RUN, "realmd.conf"), REALMD)
    write_bot_confs(RUN, os.path.join(BIN, "aiplayerbot.conf.dist"), os.path.join(BIN, "anticheat.conf.dist"),
                    a.bots, a.accounts, a.bridge_port, a.silence)
    print("serveur de test pret dans", RUN, "(%d bots, %d comptes)" % (a.bots, a.accounts))
    return 0


def write_bot_confs(run, aiplayerbot_dist, anticheat_dist, bots, accounts, bridge_port=5005, silence=(240, 480)):
    """Configs propres a playerbots dans <run> (reutilise par integrate_main.py pour le serveur principal) :
    aiplayerbot.conf, anticheat.conf, ahbot.conf (dans <run>\\..\\etc ET <run>), llm_character_card.txt."""
    write_conf(aiplayerbot_dist, os.path.join(run, "aiplayerbot.conf"),
               playerbot_overrides(bots, accounts, bridge_port, *silence))
    # Anticheat coupe comme sur le serveur principal (qui n'a pas d'anticheat.conf) : actif, il cree
    # Warden meme avec Warden.Enable = 0, et sans modules Warden la premiere connexion fait planter mangosd.
    write_conf(anticheat_dist, os.path.join(run, "anticheat.conf"), {"Enable": "0", "Warden.Enable": "0"})
    # AhBot de playerbots : sans ahbot.conf (cherche dans ../etc/), son intervalle vaut 0 et il martele
    # la base personnages a chaque tick, au point de bloquer la connexion des joueurs. On le coupe.
    etc = os.path.join(os.path.dirname(os.path.abspath(run)), "etc")
    os.makedirs(etc, exist_ok=True)
    for d in (etc, run):
        with open(os.path.join(d, "ahbot.conf"), "w", encoding="utf-8", newline="\n") as f:
            f.write("[AhBotConf]\nAhBot.Enabled = 0\nAhBot.UpdateIntervalInSeconds = 900\n")
    card = os.path.join(run, "llm_character_card.txt")
    if not os.path.exists(card):
        open(card, "w").close()   # personnalites gerees par le pont, fichier volontairement vide


if __name__ == "__main__":
    sys.exit(main())
