"""Génère server/sql/world/010_nobuild_points.sql : points d'exclusion de construction autour des villages et camps,
déduits des PNJ aubergistes (NpcFlags & 128) et maîtres de vol (NpcFlags & 8) de la base du jeu (continents 0 et 1).
Les points proches (< 60 m) sont fusionnés. usage : python tools/gen_nobuild.py"""
import subprocess, os, math
MYSQL = r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
RADIUS = 70
q = ("select c.map, round(c.position_x,1), round(c.position_y,1), ct.name, ct.NpcFlags from classicmangos.creature c "
     "join classicmangos.creature_template ct on ct.entry=c.id where c.map in (0,1) and (ct.NpcFlags & (128|8)) order by c.map, c.position_x, c.position_y")
out = subprocess.run([MYSQL, "--user=root", "--host=127.0.0.1", "--default-character-set=utf8mb4", "-N", "-e", q], capture_output=True, text=True, encoding="utf-8", check=True).stdout
pts = []
for line in out.splitlines():
    m, x, y, name, flags = line.split("\t")
    m, x, y = int(m), float(x), float(y)
    for p in pts:
        if p[0] == m and math.hypot(p[1] - x, p[2] - y) < 60:
            break
    else:
        pts.append((m, x, y, name))
rows = ",\n".join("(%d, %.1f, %.1f, %d, '%s')" % (m, x, y, RADIUS, name.replace("'", "''")) for m, x, y, name in pts)
sql = f"""-- Généré par tools/gen_nobuild.py : {len(pts)} points d'exclusion (rayon {RADIUS} m) autour des aubergistes et maîtres de vol.
CREATE TABLE IF NOT EXISTS `wowlheim_no_build_point` (
  `map` SMALLINT UNSIGNED NOT NULL, `x` FLOAT NOT NULL, `y` FLOAT NOT NULL, `radius` FLOAT NOT NULL, `name` VARCHAR(100) NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
DELETE FROM `wowlheim_no_build_point`;
INSERT INTO `wowlheim_no_build_point` (`map`,`x`,`y`,`radius`,`name`) VALUES
{rows};
"""
path = os.path.join(os.path.dirname(__file__), "..", "server", "sql", "world", "010_nobuild_points.sql")
open(path, "w", encoding="utf-8").write(sql)
print(len(pts), "points écrits dans", os.path.normpath(path))
