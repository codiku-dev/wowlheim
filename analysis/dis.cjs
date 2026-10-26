// Désassembleur CIL minimal sur les sorties REA (inspect-managed-members).
// usage: node dis.cjs members.json Type Method   (résout les tokens via les tables de la même sortie)
const fs = require('fs');
const [file, type, method] = process.argv.slice(2);
let s = fs.readFileSync(file, 'utf8');
if (s.charCodeAt(0) === 0xfeff) s = s.slice(1);
const n = JSON.parse(s).normalized_result;
const tok = new Map();
const lit = new Map();
for (const l of (n.user_strings && n.user_strings.literals) || []) lit.set(l.token, JSON.stringify(l.value));
for (const m of n.methods || []) tok.set(m.token, `${m.declaring_type}::${m.name}`);
for (const f of n.fields || []) tok.set(f.token, `${f.declaring_type}::${f.name}`);
for (const r of n.member_refs || []) tok.set(r.token, `${r.parent_name || r.declaring_type || r.class || '?'}::${r.name}`);
for (const t of n.types || []) tok.set(t.token, t.full_name);
for (const m of (n.methods || []).filter((x) => x.declaring_type === type && x.name === method)) {
  console.log(`== ${type}::${method} il_size=${m.body.il_size} sha=${m.body.il_sha256.slice(0, 12)}`);
  for (const a of m.body.anchors || []) {
    const op = a.operand;
    const r = typeof op === 'string' && lit.has(op) ? lit.get(op) : typeof op === 'string' && tok.has(op) ? tok.get(op) : op;
    console.log(`${String(a.il_offset).padStart(4)} ${a.opcode.padEnd(12)} ${r ?? ''}`);
  }
  if (m.body.truncated_instructions) console.log('TRUNCATED', m.body.truncated_instructions);
}
