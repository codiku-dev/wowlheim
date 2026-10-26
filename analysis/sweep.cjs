// Balayage de TOUS les types de assembly_valheim.dll pour retrouver les appelants (call_edges) de certains types cibles.
// Chaque type est extrait par REA dans un fichier temporaire, réduit, puis le brut est supprimé (pas de gros cache disque).
// usage: node sweep.cjs [parallélisme=4]  -> écrit valheim/callers_sweep.json
const fs = require('fs');
const os = require('os');
const path = require('path');
const cp = require('child_process');
const DLL = 'C:/Program Files (x86)/Steam/steamapps/common/Valheim/valheim_Data/Managed/assembly_valheim.dll';
const V = path.join(__dirname, 'valheim');
const TMP = process.env.SWEEP_TMP || path.join(os.tmpdir(), 'wowl_sweep');
fs.mkdirSync(TMP, { recursive: true });
const rd = (p) => { let s = fs.readFileSync(p, 'utf8'); if (s.charCodeAt(0) === 0xfeff) s = s.slice(1); return JSON.parse(s); };
const ALL = rd(path.join(V, 'members_ALL.json')).normalized_result;
const byTok = new Map(ALL.types.map((t) => [t.token, t]));
const qname = (t) => (t.enclosing_type_token ? qname(byTok.get(t.enclosing_type_token)) + '+' : '') + t.name;
const WATCH = new Set(['WearNTear', 'WearNTearUpdater', 'Piece']);
const WATCH_FIELDS = /WearNTear|clearConnected/;
// un nom nu sélectionne tous les types imbriqués du même nom : on ne lance qu'une fois par nom
const names = [...new Set(ALL.types.filter((t) => t.method_list.count > 0).map((t) => t.name))];
const outFile = path.join(V, 'callers_sweep.json');
const result = fs.existsSync(outFile) ? JSON.parse(fs.readFileSync(outFile, 'utf8')) : { done: {}, calls: [], fields: [] };
const todo = names.filter((n) => !result.done[n]);
console.log('types à balayer:', todo.length, '/', names.length);
let idx = 0, active = 0, finished = 0;
const par = parseInt(process.argv[2] || '4', 10);
function save() { fs.writeFileSync(outFile, JSON.stringify(result)); }
function next() {
  if (idx >= todo.length) { if (active === 0) { save(); console.log('fin'); } return; }
  const name = todo[idx++];
  active++;
  const f = path.join(TMP, `${idx}.json`);
  const safe = name.replace(/"/g, '');
  cp.exec(`npx --yes rea-agents@latest inspect-managed-members "${DLL}" --type "${safe}" --json > "${f}"`, { maxBuffer: 1 << 28, shell: true }, () => {
    try {
      const n = rd(f).normalized_result;
      for (const e of n.call_edges || []) if (WATCH.has(e.target_declaring_type)) result.calls.push([e.caller, e.il_offset, e.opcode, e.target_declaring_type + '::' + e.target_name]);
      for (const a of n.field_accesses || []) if (WATCH_FIELDS.test(a.field_name) || a.field_declaring_type === 'WearNTear') result.fields.push([a.method, a.il_offset, a.opcode, a.field_declaring_type + '::' + a.field_name]);
      result.done[name] = 1;
    } catch (e) { result.done[name] = 'err'; }
    try { fs.unlinkSync(f); } catch (e) {}
    active--; finished++;
    if (finished % 50 === 0) { save(); console.log(finished, '/', todo.length); }
    next();
  });
}
for (let i = 0; i < par; i++) next();
