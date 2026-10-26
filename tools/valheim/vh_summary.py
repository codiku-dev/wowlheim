import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
P=d['prefabs']
def m(n,c): 
    v=P.get(n) or {}; return (v.get('monos') or {}).get(c,[None])[0]
def piece(n):
    p=m(n,'Piece'); w=m(n,'WearNTear')
    if not p: return n+' ?'
    res=[(r['m_resItem']['name'] if r['m_resItem'] else None,r['m_amount'],r['m_recover']) for r in p['m_resources']]
    st=p['m_craftingStation']['name'] if p['m_craftingStation'] else None
    return f"{n:28s} cat={p['m_category']} {p['m_name']:32s} st={st} res={res} hp={w and w['m_health']} mat={w and w['m_materialType']}"
for n in sys.argv[2:]:
    if n.startswith('@'):
        for c,v in (P.get(n[1:]) or {}).get('monos',{}).items():
            print('##',n,c,json.dumps(v[0],ensure_ascii=False)[:2500])
    else: print(piece(n))
