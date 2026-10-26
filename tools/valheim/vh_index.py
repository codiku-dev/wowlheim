import sys,json,re
p=r"C:\Program Files (x86)\Steam\steamapps\common\Valheim\valheim_Data\StreamingAssets\SoftRef\manifest_extended"
out={}
cur={}
for line in open(p,encoding='utf-8-sig',errors='replace'):
    line=line.rstrip('\n')
    m=re.match(r'- asset ID: (\w+)',line)
    if m: cur={'id':m.group(1)};continue
    m=re.match(r'\s+bundle: (\w+)',line)
    if m and 'id' in cur: cur['bundle']=m.group(1);continue
    m=re.match(r'\s+path in bundle: (.*)',line)
    if m and 'id' in cur: out[m.group(1)]=cur['bundle']
json.dump(out,open(sys.argv[1],'w'),indent=0)
print(len(out))
