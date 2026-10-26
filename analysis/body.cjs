const fs = require('fs');
const [file, type, method] = process.argv.slice(2);
let s = fs.readFileSync(file, 'utf8');
if (s.charCodeAt(0) === 0xfeff) s = s.slice(1);
const n = JSON.parse(s).normalized_result;
const ms = n.methods.filter((m) => m.declaring_type === type && (!method || m.name === method));
for (const m of ms) {
  if (!method) { console.log(m.name, Object.keys(m.body || {}).join(',')); continue; }
  console.log(JSON.stringify(m.body, null, 1).slice(0, 12000));
}
