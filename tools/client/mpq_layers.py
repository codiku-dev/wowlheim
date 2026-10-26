r"""Lecture seule des MPQ du client 1.12.1 avec l'ordre de priorite deduit de WoW.exe (voir docs/CLIENT_FEASIBILITY.md, H2).
Ordre (du plus faible au plus fort) : dbc, speech, fonts, interface, misc, sound, wmo, terrain, texture, model
(priorites 0x36..0x3f), puis patch.MPQ (0x40), puis patch-?.MPQ en ordre croissant de nom (patch-2 = 0x41, ... , patch-Z plus fort).
base.MPQ est place le plus bas (ouverture ailleurs dans WoW.exe, non analysee) [NON VERIFIE pour sa priorite exacte].

usage:
  mpq_layers.py <DataDir> order
  mpq_layers.py <DataDir> find <regex>         # liste (archive, nom) des fichiers du (listfile) correspondants
  mpq_layers.py <DataDir> extract <outdir> <nom> [<nom>...]   # extrait avec resolution de priorite (nom avec \)
  mpq_layers.py <DataDir> extract-re <outdir> <regex>
Les fichiers extraits sont des artefacts locaux : NE PAS DISTRIBUER."""
import sys, os, re, glob
import mpyq

BASE_ORDER = ["dbc", "speech", "fonts", "interface", "misc", "sound", "wmo", "terrain", "texture", "model"]

def load_order(data_dir):
    out = []
    def p(n):
        for cand in (n + ".MPQ", n + ".mpq"):
            f = os.path.join(data_dir, cand)
            if os.path.isfile(f): return f
    b = p("base")
    if b: out.append(b)
    for n in BASE_ORDER:
        f = p(n)
        if f: out.append(f)
    f = p("patch")
    if f: out.append(f)
    extra = sorted({os.path.basename(x) for x in glob.glob(os.path.join(data_dir, "patch-?.[mM][pP][qQ]"))}, key=str.lower)
    for e in extra: out.append(os.path.join(data_dir, e))
    # Simulation (lecture seule) : WL_EXTRA_MPQ=<chemin hors client> ajoute une archive de test au sommet de la pile
    if os.environ.get("WL_EXTRA_MPQ"): out.append(os.environ["WL_EXTRA_MPQ"])
    # 'backup.MPQ' n'est PAS dans la liste de WoW.exe : volontairement ignore
    return out

class Layers:
    def __init__(self, data_dir):
        self.archives = [(os.path.basename(p), mpyq.MPQArchive(p, listfile=False)) for p in load_order(data_dir)]
    def listfile(self, a):
        try:
            return a.read_file("(listfile)").decode("latin-1").replace("\r", "").split("\n")
        except Exception:
            return []
    def has(self, a, name):
        return a.get_hash_table_entry(name) is not None
    def resolve(self, name):
        # Un bloc avec le flag 0x02000000 (MPQ_FILE_DELETE_MARKER) dans une archive de priorite superieure
        # masque le fichier des archives inferieures (constate dans patch.MPQ, ex. FrameXML\AuctionFrame.lua).
        for an, a in reversed(self.archives):
            e = a.get_hash_table_entry(name)
            if e is not None:
                if a.block_table[e.block_table_index].flags & 0x02000000:
                    return None, None
                return an, a
        return None, None
    def read(self, name):
        an, a = self.resolve(name)
        if a is None: raise FileNotFoundError(name)
        data = a.read_file(name)
        if data is None:
            e = a.get_hash_table_entry(name); b = a.block_table[e.block_table_index]
            raise ValueError(f"mpyq: lecture impossible (flags={b.flags:#x}, size={b.size}, archived={b.archived_size}) dans {an}")
        return an, data

if __name__ == "__main__":
    d, cmd = sys.argv[1], sys.argv[2]
    L = Layers(d)
    if cmd == "order":
        for i, (n, a) in enumerate(L.archives): print(i, n, "fmt", a.header["format_version"])
    elif cmd == "find":
        r = re.compile(sys.argv[3], re.I)
        for an, a in L.archives:
            for n in L.listfile(a):
                if n and r.search(n): print(an, n)
    elif cmd in ("extract", "extract-re"):
        out = sys.argv[3]
        if cmd == "extract": names = sys.argv[4:]
        else:
            r = re.compile(sys.argv[4], re.I); s = set()
            for an, a in L.archives:
                for n in L.listfile(a):
                    if n and r.search(n): s.add(n)
            names = sorted(s)
        for n in names:
            try:
                an, data = L.read(n)
            except FileNotFoundError:
                print("SUPPRIME/ABSENT", n); continue
            except Exception as e:
                print("ECHEC", n, repr(e)); continue
            dest = os.path.join(out, *n.split("\\"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "wb").write(data)
            print("OK", an, n, len(data))
