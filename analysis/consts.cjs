// Lit la table Constant (ECMA-335 §II.22.9) de assembly_valheim.dll : valeurs des constantes d'enum / champs const.
// Lecture statique des octets, rien n'est chargé ni exécuté. Sortie : valheim/constants.json {ligneChamp: valeur}
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
for (let i = 0; i < nsec; i++) {
  const o = opt + optSize + i * 40;
  secs.push({ va: u32(o + 12), vs: u32(o + 8), raw: u32(o + 20) });
}
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
const idx = (...tabs) => (tabs.some((t) => rows[t] >= 1 << 16) ? 4 : 2);
const coded = (bits, tabs) => (Math.max(...tabs.map((t) => rows[t])) >= 1 << (16 - bits) ? 4 : 2);
const sz = (t) => (rows[t] >= 1 << 16 ? 4 : 2);
const TDR = coded(2, [2, 1, 0x1b]);
const RS = coded(2, [0, 0x1a, 0x23, 1]);
const MRP = coded(3, [2, 1, 0x1a, 6, 0x1b]);
const HC = coded(2, [4, 8, 0x17]);
const rowSize = {
  0: 2 + sS + 3 * sG,
  1: RS + 2 * sS,
  2: 4 + 2 * sS + TDR + sz(4) + sz(6),
  3: sz(4),
  4: 2 + sS + sB,
  5: sz(6),
  6: 4 + 2 + 2 + sS + sB + sz(8),
  7: sz(8),
  8: 2 + 2 + sS,
  9: sz(2) + TDR,
  10: MRP + sS + sB,
  11: 2 + HC + sB,
};
let off = q;
for (let t = 0; t < 11; t++) off += rows[t] * rowSize[t];
const blob = streams['#Blob'];
const readBlob = (i) => {
  let o = blob.off + i, l = b[o];
  if (l & 0x80) { if ((l & 0xc0) === 0x80) { l = ((l & 0x3f) << 8) | b[o + 1]; o += 2; } else { l = ((l & 0x1f) << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]; o += 4; } } else o += 1;
  return b.subarray(o, o + l);
};
const out = {};
for (let i = 0; i < rows[11]; i++) {
  const o = off + i * rowSize[11];
  const ty = b[o];
  const par = HC === 4 ? u32(o + 2) : u16(o + 2);
  const bi = sB === 4 ? u32(o + 2 + HC) : u16(o + 2 + HC);
  const tag = par & 3, row = par >> 2;
  if (tag !== 0) continue; // seulement les champs
  const v = readBlob(bi);
  let val;
  switch (ty) {
    case 2: val = !!v[0]; break;
    case 4: val = v.readInt8(0); break;
    case 5: val = v[0]; break;
    case 6: val = v.readInt16LE(0); break;
    case 7: val = v.readUInt16LE(0); break;
    case 8: val = v.readInt32LE(0); break;
    case 9: val = v.readUInt32LE(0); break;
    case 10: val = String(v.readBigInt64LE(0)); break;
    case 11: val = String(v.readBigUInt64LE(0)); break;
    case 12: val = v.readFloatLE(0); break;
    case 13: val = v.readDoubleLE(0); break;
    case 14: val = v.toString('utf16le'); break;
    default: val = null;
  }
  out[row] = val;
}
fs.writeFileSync(path.join(__dirname, 'valheim', 'constants.json'), JSON.stringify(out));
console.log('constantes de champs:', Object.keys(out).length, ' (table Constant:', rows[11], 'lignes)');
