// Outil d'extraction CIL avec résolution globale des jetons (méthodes/champs de tous les types).
// usage:
//   node rea.cjs dis <Type> <Methode|*> [--stdout]   écrit valheim/dis/<Type>.<Methode>.txt
//   node rea.cjs callers <Type> <Methode>           liste les méthodes (des types déjà extraits) qui appellent Type::Methode
//   node rea.cjs fields <Type>                      champs du type (nom, type, constante éventuelle)
//   node rea.cjs strings <Type>                     littéraux ldstr chargés par le type
// La table des types (valheim/members_ALL.json) donne les plages de lignes méthode/champ de chaque type,
// ce qui permet de retrouver le type propriétaire d'un jeton 0x06…/0x04… puis de l'extraire à la demande.
const fs = require('fs');
const path = require('path');
const cp = require('child_process');
const os = require('os');
const DLL = 'C:/Program Files (x86)/Steam/steamapps/common/Valheim/valheim_Data/Managed/assembly_valheim.dll';
const V = path.join(__dirname, 'valheim');
const CACHE = process.env.REA_CACHE || path.join(os.tmpdir(), 'wowl_rea_cache');
fs.mkdirSync(CACHE, { recursive: true });
fs.mkdirSync(path.join(V, 'dis'), { recursive: true });
const rd = (p) => {
  let s = fs.readFileSync(p, 'utf8');
  if (s.charCodeAt(0) === 0xfeff) s = s.slice(1);
  return JSON.parse(s);
};
const ALL = rd(path.join(V, 'members_ALL.json')).normalized_result;
const TYPES = ALL.types;
const byTok = new Map(TYPES.map((t) => [t.token, t]));
const qname = (t) => (t.enclosing_type_token ? qname(byTok.get(t.enclosing_type_token)) + '+' : '') + t.name;
const mranges = TYPES.filter((t) => t.method_list.count).map((t) => ({ a: t.method_list.first_row, b: t.method_list.last_row, t }));
const franges = TYPES.filter((t) => t.field_list.count).map((t) => ({ a: t.field_list.first_row, b: t.field_list.last_row, t }));
const owner = (ranges, row) => (ranges.find((r) => row >= r.a && row <= r.b) || {}).t;
const tokFile = path.join(V, 'tokens.json');
const TOK = fs.existsSync(tokFile) ? JSON.parse(fs.readFileSync(tokFile, 'utf8')) : {};
const CONST = fs.existsSync(path.join(V, 'constants.json')) ? JSON.parse(fs.readFileSync(path.join(V, 'constants.json'), 'utf8')) : {};
const DLLB = fs.readFileSync(DLL);
function switchTargets(m, a) {
  const fo = m.body.file_offset;
  const fat = (DLLB[fo] & 3) === 3;
  const cs = fo + (fat ? ((DLLB[fo + 1] >> 4) * 4) : 1);
  if (DLLB[cs + a.il_offset] !== 0x45) return null;
  const n = DLLB.readUInt32LE(cs + a.il_offset + 1);
  const base = a.il_offset + 5 + 4 * n;
  const t = [];
  for (let i = 0; i < n; i++) t.push(base + DLLB.readInt32LE(cs + a.il_offset + 5 + 4 * i));
  return t;
}
const STR = {}; // ldstr résolus
const saveTok = () => fs.writeFileSync(tokFile, JSON.stringify(TOK));
const done = new Set(Object.keys(TOK.__done || {}));
TOK.__done = TOK.__done || {};

function extract(t) {
  const f = path.join(CACHE, `${t.token}.json`);
  if (!fs.existsSync(f)) {
    cp.execSync(`npx --yes rea-agents@latest inspect-managed-members "${DLL}" --type "${t.name}" --json > "${f}"`, { maxBuffer: 1 << 30, stdio: ['ignore', 'inherit', 'ignore'], shell: true });
  }
  return f;
}
function absorb(t) {
  if (TOK.__done[t.token]) return;
  const n = rd(extract(t)).normalized_result;
  for (const m of n.methods || []) {
    const ot = byTok.get(m.declaring_type_token);
    const ps = (m.signature && m.signature.parameter_types) || [];
    TOK[m.token] = `${qname(ot)}::${m.name}(${ps.join(',')})`;
  }
  for (const f of n.fields || []) TOK[f.token] = `${qname(byTok.get(f.declaring_type_token))}::${f.name}`;
  TOK.__done[t.token] = 1;
  saveTok();
}
const MR = {};
for (const r of []) MR[r.token] = r;
function resolveTok(op) {
  if (typeof op !== 'string' || !/^0x[0-9a-f]{8}$/i.test(op)) return op;
  const hi = op.slice(0, 4).toLowerCase();
  const row = parseInt(op.slice(4), 16);
  if (hi === '0x06' || hi === '0x04') {
    if (!TOK[op]) {
      const t = owner(hi === '0x06' ? mranges : franges, row);
      if (t) absorb(t);
    }
    return TOK[op] || op;
  }
  if (hi === '0x02') return byTok.has(op) ? qname(byTok.get(op)) : op;
  return TOK[op] || op;
}

function loadType(name) {
  const t = TYPES.find((x) => qname(x) === name || x.full_name === name) || TYPES.find((x) => x.name === name);
  if (!t) throw new Error('type inconnu ' + name);
  // fichier principal du type : analysis/valheim/members_<Type>.json (réutilise l'existant)
  let f = path.join(V, `members_${name}.json`);
  if (!fs.existsSync(f)) f = extract(t);
  const n = rd(f).normalized_result;
  // vérifie que TOK est alimenté par ce type
  absorb(t);
  const lit = {};
  for (const l of (n.user_strings && n.user_strings.literals) || []) lit[l.token] = l.value;
  const mr = {};
  for (const r of n.member_refs || []) mr[r.token] = `${r.parent_name || '?'}::${r.name}`;
  const edges = {};
  for (const e of n.call_edges || []) edges[`${e.caller_token}:${e.il_offset}`] = `${e.target_declaring_type}::${e.target_name}<T>`;
  return { t, n, lit, mr, edges };
}
function fmtOp(a, ctx, mtok) {
  if (typeof a.operand === 'string' && /^0x2b/i.test(a.operand) && ctx.edges[`${mtok}:${a.il_offset}`]) return ctx.edges[`${mtok}:${a.il_offset}`];
  const op = a.operand;
  if (op === null || op === undefined) return '';
  if (typeof op === 'string' && /^0x70/i.test(op)) return ctx.lit[op] !== undefined ? JSON.stringify(ctx.lit[op]) : `<str ${op}>`;
  if (typeof op === 'string' && /^0x0a/i.test(op) && ctx.mr[op]) return ctx.mr[op];
  if (typeof op === 'object') return JSON.stringify(op);
  const r = resolveTok(op);
  return r;
}
function disMethod(ctx, m) {
  const ps = (m.signature && m.signature.parameter_types) || [];
  const out = [`== ${qname(ctx.t)}::${m.name}(${ps.join(', ')}) -> ${m.signature && m.signature.return_type}  il_size=${m.body.il_size} sha=${m.body.il_sha256.slice(0, 12)}`];
  if (m.body.max_stack !== undefined) out.push(`   locals_sig=${m.body.local_var_sig_token}`);
  for (const a of m.body.anchors || []) {
    let o = fmtOp(a, ctx, m.token);
    if (a.opcode === 'switch') { const t = switchTargets(m, a); o = t ? `[${t.map((x, i) => i + ':' + x).join(' ')}]` : o; }
    out.push(`${String(a.il_offset).padStart(4)} ${a.opcode.padEnd(12)} ${o}`);
  }
  if (m.body.truncated_instructions) out.push('TRUNCATED ' + m.body.truncated_instructions);
  return out.join('\n');
}
const [cmd, type, meth, flag] = process.argv.slice(2);
if (cmd === 'dis') {
  const ctx = loadType(type);
  const ms = ctx.n.methods.filter((m) => m.declaring_type_token === ctx.t.token || m.declaring_type === type).filter((m) => meth === '*' || m.name === meth);
  if (!ms.length) { console.error('méthode introuvable'); process.exit(1); }
  const txt = ms.map((m) => disMethod(ctx, m)).join('\n\n') + '\n';
  if (flag === '--stdout') process.stdout.write(txt);
  else {
    const o = path.join(V, 'dis', `${type.replace(/[+/]/g, '.')}.${meth === '*' ? '_all' : meth}.txt`);
    fs.writeFileSync(o, txt);
    console.log('écrit', o, txt.length);
  }
} else if (cmd === 'fields') {
  const ctx = loadType(type);
  for (const f of ctx.n.fields) if (f.declaring_type_token === ctx.t.token) { const c = CONST[parseInt(f.token.slice(4), 16)]; console.log(f.token, f.name, f.signature.field_type, c !== undefined ? '= ' + JSON.stringify(c) : ''); }
} else if (cmd === 'strings') {
  const ctx = loadType(type);
  for (const [k, v] of Object.entries(ctx.lit)) console.log(k, JSON.stringify(v));
} else if (cmd === 'callers') {
  // cherche dans tous les caches
  const target = `${type}::${meth}`;
  for (const t of TYPES) {
    const f = path.join(CACHE, `${t.token}.json`);
    if (!fs.existsSync(f)) continue;
    const n = rd(f).normalized_result;
    const ctx = { lit: {}, mr: {} };
    for (const m of n.methods || []) {
      if (m.declaring_type_token !== t.token) continue;
      for (const a of (m.body && m.body.anchors) || []) {
        if (/^call/.test(a.opcode)) {
          const r = resolveTok(a.operand);
          if (typeof r === 'string' && r.startsWith(target)) console.log(`${qname(t)}::${m.name} @${a.il_offset} ${r}`);
        }
      }
    }
  }
}
