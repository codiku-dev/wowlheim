"""usage: python type.py ACTIONS...   (fenetre WoW de client_test mise au premier plan ; actions dans l'ordre)
  --click X,Y   clic gauche (coord. client)   --dclick X,Y   --key NOM   --text TXT   --sleep S
  --shot FICHIER.png   --textfile F (saisit le contenu du fichier, jamais affiche)"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wgui

hwnd, pid = wgui.find_wow()
if not hwnd:
    sys.exit('fenetre WoW (client_test) introuvable')
print('foreground:', wgui.foreground(hwnd))
wgui.GUARD = hwnd
a = sys.argv[1:]
i = 0
while i < len(a):
    o, v = a[i], a[i + 1]
    i += 2
    if o != '--sleep' and o != '--shot' and not wgui.ensure_fg(hwnd):
        sys.exit('ABANDON : la fenetre WoW n est pas au premier plan, aucune entree envoyee')
    if o == '--click':
        x, y = map(int, v.split(',')); wgui.click(hwnd, x, y)
    elif o == '--dclick':
        x, y = map(int, v.split(',')); wgui.click(hwnd, x, y, double=True)
    elif o == '--hold':
        k, secs = v.split(','); wgui.hold(k, float(secs))
    elif o == '--move':
        x, y = map(int, v.split(',')); wgui.mouse_move(hwnd, x, y)
    elif o == '--mclick':
        x, y = map(int, v.split(',')); wgui.click(hwnd, x, y, button='middle')
    elif o == '--rclick':
        x, y = map(int, v.split(',')); wgui.click(hwnd, x, y, button='right')
    elif o == '--wheel':
        x, y, n = map(int, v.split(',')); wgui.wheel(hwnd, x, y, n)
    elif o == '--drag':
        x1, y1, x2, y2 = map(int, v.split(',')); wgui.drag(hwnd, x1, y1, x2, y2)
    elif o == '--key':
        for k in v.split('+') if False else [v]:
            wgui.key(k)
    elif o == '--text':
        if os.environ.get('WL_TYPE') == 'keys':
            wgui.type_text(v)
        else:
            wgui.paste_text(v)               # copier-coller (Ctrl+V) : bien plus rapide que la frappe
    elif o == '--keys':
        wgui.type_text(v)
    elif o == '--textfile':
        wgui.type_text(open(v, encoding='utf-8').read().strip())
    elif o == '--sleep':
        time.sleep(float(v))
    elif o == '--shot':
        print('shot', v, '%.3f' % wgui.capture(v, hwnd))
    else:
        sys.exit('option inconnue ' + o)
