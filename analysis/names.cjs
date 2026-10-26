const fs=require('fs');const re=new RegExp(process.argv[3],'i');
let s=fs.readFileSync(process.argv[2],'utf8').replace(/^﻿/,'');const n=JSON.parse(s).normalized_result;
console.log('types:',(n.types||[]).map(t=>t.full_name).join(','));
console.log('fields:',(n.fields||[]).filter(f=>re.test(f.name)).map(f=>f.declaring_type+'::'+f.name).join(', '));
console.log('methods:',(n.methods||[]).filter(f=>re.test(f.name)).map(f=>f.declaring_type+'::'+f.name).join(', '));
