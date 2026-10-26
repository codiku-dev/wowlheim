// Balayage binaire exhaustif des corps IL de assembly_valheim.dll : appelants directs (call/callvirt/newobj/ldftn) des
// méthodes de types cibles et accès (ld/st fld/sfld) à des champs nommés, SANS passer par REA (une seule passe, ~1 s).
// Décodage linéaire des instructions (table des tailles d'opérandes ECMA-335), tables de métadonnées lues dans les octets du DLL.
// usage: node callscan.cjs Type1,Type2 [champRegex]   -> écrit valheim/callers_<Type1>.json et affiche les résultats
const fs = require('fs');
const path = require('path');
const DLL = 'C:/Program Files (x86)/Steam/steamapps/common/Valheim/valheim_Data/Managed/assembly_valheim.dll';
const b = fs.readFileSync(DLL);
const u16 = (o) => b.readUInt16LE(o), u32 = (o) => b.readUInt32LE(o);
const pe = u32(0x3c);
const nsec = u16(pe + 6), optSize = u16(pe + 20);
const opt = pe + 24;
const magic = u16(opt);
const dd = opt + (magic === 0x20b ? 112 : 96);
const cliRva = u32(dd + 14 * 8);
const secs = [];
for (let i = 0; i < nsec; i++) { const o = opt + optSize + i * 40; secs.push({ va: u32(o + 12), vs: u32(o + 8), raw: u32(o + 20) }); }
const r2o = (rva) => { const s = secs.find((s) => rva >= s.va && rva < s.va + Math.max(s.vs, 1)); return s.raw + (rva - s.va); };
const cli = r2o(cliRva);
const mdRoot = r2o(u32(cli + 8));
const vlen = u32(mdRoot + 12);
let p = mdRoot + 16 + vlen;
const nstreams = u16(p + 2);
p += 4;
const streams = {};
for (let i = 0; i < nstreams; i++) {
  const off = u32(p), size = u32(p + 4);
  let name = '', q = p + 8;
  while (b[q]) name += String.fromCharCode(b[q++]);
  q++;
  while ((q - p) % 4) q++;
  streams[name] = { off: mdRoot + off, size };
  p = q;
}
const T = streams['#~'];
const heap = b[T.off + 6];
const sS = heap & 1 ? 4 : 2, sG = heap & 2 ? 4 : 2, sB = heap & 4 ? 4 : 2;
const valid = b.readBigUInt64LE(T.off + 8);
let q = T.off + 24;
const rows = new Array(64).fill(0);
for (let i = 0; i < 64; i++) if ((valid >> BigInt(i)) & 1n) { rows[i] = u32(q); q += 4; }
const coded = (bits, tabs) => (Math.max(...tabs.map((t) => rows[t])) >= 1 << (16 - bits) ? 4 : 2);
const sz = (t) => (rows[t] >= 1 << 16 ? 4 : 2);
const TDR = coded(2, [2, 1, 0x1b]);
const RS = coded(2, [0, 0x1a, 0x23, 1]);
const rowSize = { 0: 2 + sS + 3 * sG, 1: RS + 2 * sS, 2: 4 + 2 * sS + TDR + sz(4) + sz(6), 3: sz(4), 4: 2 + sS + sB, 5: sz(6), 6: 4 + 2 + 2 + sS + sB + sz(8) };
const tabOff = {};
let off = q;
for (let t = 0; t < 7; t++) { tabOff[t] = off; off += rows[t] * rowSize[t]; }
const str = (i) => { let o = streams['#Strings'].off + i, e = o; while (b[e]) e++; return b.toString('utf8', o, e); };
const rd = (o, n) => (n === 4 ? u32(o) : u16(o));
// TypeDef
const types = [];
for (let i = 0; i < rows[2]; i++) {
  const o = tabOff[2] + i * rowSize[2];
  types.push({ name: str(rd(o + 4, sS)), field: rd(o + 4 + 2 * sS + TDR, sz(4)), method: rd(o + 4 + 2 * sS + TDR + sz(4), sz(6)) });
}
const methods = [];
for (let i = 0; i < rows[6]; i++) {
  const o = tabOff[6] + i * rowSize[6];
  methods.push({ rva: u32(o), name: str(rd(o + 8, sS)), type: null });
}
const fields = [];
for (let i = 0; i < rows[4]; i++) { const o = tabOff[4] + i * rowSize[4]; fields.push({ name: str(rd(o + 2, sS)), type: null }); }
for (let i = 0; i < types.length; i++) {
  const m0 = types[i].method - 1, m1 = (i + 1 < types.length ? types[i + 1].method : rows[6] + 1) - 1;
  for (let m = m0; m < m1; m++) methods[m].type = types[i].name;
  const f0 = types[i].field - 1, f1 = (i + 1 < types.length ? types[i + 1].field : rows[4] + 1) - 1;
  for (let f = f0; f < f1; f++) fields[f].type = types[i].name;
}
// opérandes
const sz1 = new Set([0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x1f, 0xde]);
for (let o = 0x2b; o <= 0x37; o++) sz1.add(o);
const sz4 = new Set([0x20, 0x22, 0x27, 0x28, 0x29, 0x6f, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x79, 0x7b, 0x7c, 0x7d, 0x7e, 0x7f, 0x80, 0x81, 0x8c, 0x8d, 0x8f, 0xa3, 0xa4, 0xa5, 0xc2, 0xc6, 0xd0, 0xdd]);
for (let o = 0x38; o <= 0x44; o++) sz4.add(o);
const fe4 = new Set([0x06, 0x07, 0x15, 0x16, 0x1c]), fe2 = new Set([0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e]), fe1 = new Set([0x12]);
const targets = new Set(process.argv[2].split(','));
const fre = process.argv[3] ? new RegExp(process.argv[3]) : null;
const calls = [], facc = [];
let nbody = 0;
for (let mi = 0; mi < methods.length; mi++) {
  const m = methods[mi];
  if (!m.rva) continue;
  const o = r2o(m.rva);
  const h = b[o];
  let size, code;
  if ((h & 3) === 2) { size = h >> 2; code = o + 1; } else { size = u32(o + 4); code = o + ((b[o + 1] >> 4) * 4); }
  nbody++;
  const tryM = (tok, at, kind) => {
    if (tok >>> 24 !== 0x06) return;
    const t = methods[(tok & 0xffffff) - 1];
    if (t && targets.has(t.type)) calls.push(`${m.type}::${m.name} @${at} ${kind} ${t.type}::${t.name}`);
  };
  const tryF = (tok, at, kind) => {
    if (tok >>> 24 !== 0x04) return;
    const f = fields[(tok & 0xffffff) - 1];
    if (f && fre.test(f.name)) facc.push(`${m.type}::${m.name} @${at} ${kind} ${f.type}::${f.name}`);
  };
  let i = 0;
  while (i < size) {
    const at = i;
    const op = b[code + i++];
    if (op === 0xfe) {
      const op2 = b[code + i++];
      if (fe4.has(op2)) { const tok = u32(code + i); i += 4; if (op2 === 0x06 || op2 === 0x07) tryM(tok, at, 'ldftn'); }
      else if (fe2.has(op2)) i += 2;
      else if (fe1.has(op2)) i += 1;
      continue;
    }
    if (op === 0x45) { const n = u32(code + i); i += 4 + 4 * n; continue; }
    if (sz1.has(op)) { i += 1; continue; }
    if (op === 0x21 || op === 0x23) { i += 8; continue; }
    if (sz4.has(op)) {
      const tok = u32(code + i); i += 4;
      if (op === 0x28 || op === 0x6f || op === 0x73) tryM(tok, at, op === 0x28 ? 'call' : op === 0x6f ? 'callvirt' : 'newobj');
      else if (op >= 0x7b && op <= 0x80 && fre) tryF(tok, at, { 0x7b: 'ldfld', 0x7c: 'ldflda', 0x7d: 'stfld', 0x7e: 'ldsfld', 0x7f: 'ldsflda', 0x80: 'stsfld' }[op]);
    }
  }
}
const out = { corps: nbody, calls, fields: facc };
const f = path.join(__dirname, 'valheim', `callers_${process.argv[2].split(',')[0]}.json`);
fs.writeFileSync(f, JSON.stringify(out, null, 1));
console.log('corps de méthodes décodés:', nbody, '| appels:', calls.length, '| accès champs:', facc.length);
for (const c of calls) console.log(c);
for (const c of facc) console.log('F', c);
