import sys,json; import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import vh_dump as D
e=D.e
# hammer piece table
go=D.e.container['Assets/GameElements/Items/tools/Hammer.prefab'].read()
pieces=[]
for c in go.m_Component:
    o=c.component.deref()
    if o.type.name!='MonoBehaviour': continue
    m=o.read()
    if hasattr(m,'m_itemData'):
        pt=m.m_itemData.m_shared.m_buildPieces.deref().read()
        table=D.conv(pt); 
        pieces=[p.deref().read().m_Name for p in pt.m_pieces]
out={'hammer_table':table,'hammer_pieces':pieces,'prefabs':{}}
trees=['Beech1','Beech_small1','Birch1','Birch2','Oak1','FirTree','FirTree_small','Pinetree_01','Beech_Stub','Birch1_aut','SwampTree1',
 'beech_log','beech_log_half','Birch_log','Birch_log_half','Oak_log','Oak_log_half','FirTree_log','FirTree_log_half','PineTree_log','PineTree_log_half',
 'rock1','rock2','rock3','rock4','Rock_3','Rock_4','Rock_7','MineRock_Copper','MineRock_Tin','rock4_copper','MineRock_Stone',
 'rock4_copper_frac','rock4_coast','rock4_coast_frac','mudpile','mudpile_frac','silvervein','silvervein_frac',
 'Hammer','Hoe','Cultivator','AxeStone','AxeFlint','AxeBronze','AxeIron','AxeBlackMetal','AxeJotunBane','PickaxeAntler','PickaxeBronze','PickaxeIron','PickaxeBlackMetal','PickaxeStone',
 'Wood','FineWood','RoundLog','CopperOre','TinOre','IronScrap','SilverOre','IronOre','ElderBark','YggdrasilWood','Stone','Flint','Resin','DeerHide','LeatherScraps','Copper','Tin','Bronze','Iron','BronzeNails','IronNails','TrophyDeer','Coal','Silver','BlackMetal','Obsidian','Crystal','LinenThread','LoxPelt','WolfPelt','TrollHide','Chitin','SurtlingCore','GreydwarfEye','BoneFragments','Guck','Tar','Feathers','HardAntler','Raspberry','Honey','Thistle','Dandelion','Mushroom','AncientSeed']
names=list(dict.fromkeys(pieces+trees))
for i,n in enumerate(names):
    try: out['prefabs'][n]=D.dump(n)
    except Exception as ex: out['prefabs'][n]={'error':repr(ex)}
    if i%25==0: print(i,len(names),flush=True)
# recipes (ScriptableObject MonoBehaviours with m_item + m_resources + m_craftingStation)
recs=[]
for path,p in e.container.items():
    pass
for o in e.objects:
    if o.type.name!='MonoBehaviour': continue
    try:
        n=o.peek_name()
    except Exception: n=None
    if not n or not n.startswith('Recipe_'): continue
    try: recs.append(D.conv(o.read()))
    except Exception as ex: recs.append({'name':n,'err':repr(ex)})
out['recipes']=recs
json.dump(out,open(sys.argv[1],'w',encoding='utf-8'),indent=1,ensure_ascii=False,default=str)
print('done',len(names),len(recs))
