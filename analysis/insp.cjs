const fs = require('fs');
const rd = (p) => JSON.parse(fs.readFileSync(p, 'utf8').charCodeAt(0) === 0xfeff ? fs.readFileSync(p, 'utf8').slice(1) : fs.readFileSync(p, 'utf8'));
for (const t of ['WearNTear', 'Piece', 'Cover', 'EnvMan', 'Player']) {
  const n = rd(`valheim/members_${t}.json`).normalized_result;
  const ty = (n.types || []).filter((x) => x.full_name === t);
  const f = (n.fields || []).filter((x) => x.declaring_type === t);
  const m = (n.methods || []).filter((x) => x.declaring_type === t);
  console.log(`## ${t} types=${ty.length} fields=${f.length} methods=${m.length}`);
  if (t === 'WearNTear' || t === 'Cover') {
    console.log('F:', f.map((x) => x.name).join(', '));
    console.log('M:', m.map((x) => x.name).join(', '));
  }
  if (t === 'WearNTear' && n.methods[0]) console.log('method keys:', Object.keys(n.methods[0]).join(','));
}
