"""Verifie la SYNTAXE d'un .lua avec Lua 5.1 (lupa) -- approximation de 5.0 (pas de Lua 5.0 disponible) -- et
signale les constructions interdites en 5.0 : '#', '%' (operateur arithmetique), select, string.match/gmatch, '...' en table.
usage: luacheck_syntax.py fichier.lua"""
import sys, re
try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    from lupa import LuaRuntime
src = open(sys.argv[1], encoding="utf-8").read()
lua = LuaRuntime(unpack_returned_tuples=True)
f, err = lua.eval("function(s) local f, e = loadstring(s); return f ~= nil, e end")(src)
print("syntaxe Lua 5.1:", "OK" if f else "ERREUR " + str(err))
# retire commentaires et chaines avant de chercher les constructions interdites
s = re.sub(r"--[^\n]*", "", src)
s = re.sub(r'"(\\.|[^"\\])*"', '""', s)
bad = []
for pat, why in [(r"(?<![\w\)\]])#\s*\w", "operateur # (absent en 5.0)"), (r"\bselect\s*\(", "select (absent en 5.0)"),
                 (r"\.match\s*\(|\bgmatch\b", "string.match/gmatch (absents en 5.0)"), (r"\bhooksecurefunc\b", "hooksecurefunc (absent)"),
                 (r"\w\s%\s\w", "operateur % arithmetique ? (verifier ; math.mod en 5.0)")]:
    for m in re.finditer(pat, s): bad.append((why, s[max(0, m.start()-20):m.end()+20].replace("\n", " ")))
print("constructions suspectes:", bad if bad else "aucune")
