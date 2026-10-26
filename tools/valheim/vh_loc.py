import UnityPy,sys,re
env=UnityPy.load(r"C:\Program Files (x86)\Steam\steamapps\common\Valheim\valheim_Data\resources.assets")
for o in env.objects:
    if o.type.name=='TextAsset':
        t=o.read()
        s=t.m_Script if isinstance(t.m_Script,str) else t.m_Script.decode('utf-8','replace')
        if 'piece_woodfloor2x2' in s:
            print(t.m_Name,len(s)); print(s[:600])
            open(sys.argv[1]+'/'+t.m_Name+'.txt','w',encoding='utf-8').write(s)
