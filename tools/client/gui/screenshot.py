"""usage: python screenshot.py <sortie.png> [--screen] [--pw]   (capture la fenetre WoW de client_test)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wgui

out = sys.argv[1]
hwnd, pid = wgui.find_wow()
if '--screen' in sys.argv or not hwnd:
    print('plein ecran, non-noir=%.3f' % wgui.capture(out, None, True))
elif '--pw' in sys.argv:
    print('PrintWindow ok/non-noir =', wgui.printwindow(out, hwnd))
else:
    print('fenetre pid=%s rect=%s non-noir=%.3f' % (pid, wgui.client_rect(hwnd), wgui.capture(out, hwnd)))
