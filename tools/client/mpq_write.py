r"""Ecriture d'archives MPQ v1 (format 0, en-tete 0x20) en Python pur -- aucune solution PyPI fiable n'existe
pour ECRIRE (voir docs/CLIENT_FEASIBILITY.md H2). Implemente la specification publique du format MPQ
(table de chiffrement, hash de noms, tables hash/block chiffrees), fichiers soit stockes bruts, soit compresses
zlib par secteurs. Pas de chiffrement de fichiers, pas de CRC de secteurs, pas de patch-files.

NOTE : le mode compress=False (fichiers bruts, sans table de secteurs, conforme a la spec/StormLib) ne peut PAS
etre relu par mpyq (il suppose toujours une table de secteurs) ; utiliser compress=True (defaut du test).
API : write_mpq(path, {nom_mpq: bytes}, compress=True, hash_size=None, listfile=True)
Verification : mpq_roundtrip_test.py relit l'archive avec mpyq (implementation independante).
LIMITE : la compatibilite avec le vrai WoW.exe 5875 n'est PAS verifiee (pas de test en jeu possible)."""
import struct, zlib

def _crypt_table():
    t = [0] * 0x500
    seed = 0x00100001
    for i1 in range(0x100):
        i2 = i1
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            a = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            b = seed & 0xFFFF
            t[i2] = a | b
            i2 += 0x100
    return t
_T = _crypt_table()
M = 0xFFFFFFFF

def mpq_hash(name, htype):
    s1, s2 = 0x7FED7FED, 0xEEEEEEEE
    for c in name.upper().replace("/", "\\"):
        ch = ord(c)
        s1 = _T[htype * 0x100 + ch] ^ ((s1 + s2) & M)
        s2 = (ch + s1 + s2 + ((s2 << 5) & M) + 3) & M
    return s1

def encrypt_block(words, key):
    seed = 0xEEEEEEEE
    out = []
    for w in words:
        seed = (seed + _T[0x400 + (key & 0xFF)]) & M
        out.append(w ^ ((key + seed) & M))
        key = ((((~key) & M) << 21) + 0x11111111) & M | (key >> 11)
        seed = (w + seed + ((seed << 5) & M) + 3) & M
    return out

def _enc_table(raw, key_name):
    assert len(raw) % 4 == 0
    words = list(struct.unpack("<%dI" % (len(raw) // 4), raw))
    return struct.pack("<%dI" % len(words), *encrypt_block(words, mpq_hash(key_name, 3)))

FLAG_EXISTS, FLAG_COMPRESS = 0x80000000, 0x00000200

def write_mpq(path, files, compress=True, hash_size=None, listfile=True, sector_shift=3):
    files = dict(files)
    if listfile:
        files["(listfile)"] = ("\r\n".join(k for k in files) + "\r\n").encode("latin-1")
    n = len(files)
    if hash_size is None:
        hash_size = 16
        while hash_size < n * 2: hash_size *= 2
    assert hash_size & (hash_size - 1) == 0 and hash_size >= n
    sector = 512 << sector_shift
    body = bytearray()
    blocks = []
    pos = 0x20
    for name, data in files.items():
        flags = FLAG_EXISTS
        if compress and len(data) > 0:
            nsec = (len(data) + sector - 1) // sector
            chunks = []
            for i in range(nsec):
                raw = data[i * sector:(i + 1) * sector]
                z = zlib.compress(raw, 9)
                chunks.append(b"\x02" + z if len(z) + 1 < len(raw) else raw)   # 0x02 = zlib ; sinon secteur brut
            table_len = 4 * (nsec + 1)
            offs = [table_len]
            for c in chunks: offs.append(offs[-1] + len(c))
            blob = struct.pack("<%dI" % (nsec + 1), *offs) + b"".join(chunks)
            flags |= FLAG_COMPRESS   # meme si aucun secteur ne gagne de place (secteurs bruts, comme dans les MPQ officiels)
        else:
            blob = data
        blocks.append((pos, len(blob), len(data), flags))
        body += blob
        pos += len(blob)
    # table de hash
    HT = [(M, M, 0xFFFF, 0xFFFF, M)] * hash_size   # vide : block_index = 0xFFFFFFFF
    HT = list(HT)
    for bi, name in enumerate(files):
        h = mpq_hash(name, 0) & (hash_size - 1)
        while HT[h][4] != M:
            h = (h + 1) & (hash_size - 1)
        HT[h] = (mpq_hash(name, 1), mpq_hash(name, 2), 0, 0, bi)   # locale neutre 0, plateforme 0
    hraw = b"".join(struct.pack("<IIHHI", *e) for e in HT)
    braw = b"".join(struct.pack("<IIII", *b) for b in blocks)
    hash_off = pos
    block_off = hash_off + len(hraw)
    total = block_off + len(braw)
    header = struct.pack("<4sIIHHIIII", b"MPQ\x1a", 0x20, total, 0, sector_shift, hash_off, block_off, hash_size, n)
    with open(path, "wb") as f:
        f.write(header); f.write(body)
        f.write(_enc_table(hraw, "(hash table)"))
        f.write(_enc_table(braw, "(block table)"))
    return total
