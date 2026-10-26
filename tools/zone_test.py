import sys, time, re
from wlclient import Session, login_char
s = Session(sys.argv[1], sys.argv[2]); login_char(s, 'Wlzone')
def say(c, t=1.2): return [l for l in s.say(c, t) if 'Welcome to' not in l and 'Tickets' not in l]
ok = True
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(('[OK]   ' if cond else '[ÉCHEC]'), name, detail)
say('.build nocost on')
for place, expect_refused in (('Stormwind', True), ('Orgrimmar', True), ('Ironforge', True), ('Goldshire', True), ('RazorHill', True), ('Kharanos', True), ('WesternPlaguelands', False), ('DunMorogh', True), ('Westfall', False)):
    print(place, 'téléport', s.teleport(place))
    r = say('.build place Plancher 3 0 0')
    refused = any('refusée' in l for l in r)
    check(f'{place} : construction {"interdite" if expect_refused else "autorisée"}', refused == expect_refused, ' '.join(r))
    if not refused:
        r2 = say('.build remove'); print(r2)
print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
s.close()
