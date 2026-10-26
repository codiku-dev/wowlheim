-- Wowlheim : catalogue des pièces de construction, coûts, recettes, zones (base world). Rejouable.
DROP TABLE IF EXISTS `wowlheim_piece_cost`;
DROP TABLE IF EXISTS `wowlheim_piece_template`;
CREATE TABLE `wowlheim_piece_template` (
  `id` INT UNSIGNED NOT NULL PRIMARY KEY,
  `name` VARCHAR(64) NOT NULL,
  `gameobject_entry` INT UNSIGNED NOT NULL,
  `material` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'index MaterialType Valheim (docs/VALHEIM_RULES.md 1.1)',
  `max_health` INT UNSIGNED NOT NULL DEFAULT 200,
  `supports` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  `requires_workbench` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `kind` VARCHAR(16) NOT NULL DEFAULT 'floor',
  `sx` FLOAT NOT NULL DEFAULT 1 COMMENT 'dimensions de la boîte de collision logique (m) : largeur locale x',
  `sy` FLOAT NOT NULL DEFAULT 1 COMMENT 'profondeur locale y',
  `sz` FLOAT NOT NULL DEFAULT 1 COMMENT 'hauteur',
  `ext_station` VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'pour kind=extension : station visée (docs/VALHEIM_RULES.md 8)',
  `ext_distance` FLOAT NOT NULL DEFAULT 5 COMMENT 'StationExtension.m_maxStationDistance (défaut du constructeur : 5)',
  `ext_stack` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'StationExtension.m_stack : plusieurs exemplaires comptés'
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE `wowlheim_piece_cost` (
  `piece_id` INT UNSIGNED NOT NULL,
  `item_id` INT UNSIGNED NOT NULL,
  `count` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`piece_id`, `item_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- Zones où la construction est interdite en plus des drapeaux de zone (capitales/villes/arènes) ; `area_id` = AreaTable.
CREATE TABLE IF NOT EXISTS `wowlheim_forbidden_area` (
  `area_id` INT UNSIGNED NOT NULL PRIMARY KEY,
  `name` VARCHAR(64) NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- Recettes d'établi (outils, etc.) et leurs ingrédients
DROP TABLE IF EXISTS `wowlheim_recipe_ingredient`;
DROP TABLE IF EXISTS `wowlheim_recipe`;
CREATE TABLE `wowlheim_recipe` (
  `id` INT UNSIGNED NOT NULL PRIMARY KEY,
  `name` VARCHAR(64) NOT NULL,
  `station` VARCHAR(16) NOT NULL DEFAULT 'workbench',
  `output_item` INT UNSIGNED NOT NULL,
  `output_count` INT UNSIGNED NOT NULL DEFAULT 1,
  `min_station_level` TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'Recipe.m_minStationLevel : niveau de la station requis'
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
CREATE TABLE `wowlheim_recipe_ingredient` (
  `recipe_id` INT UNSIGNED NOT NULL,
  `item_id` INT UNSIGNED NOT NULL,
  `count` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`recipe_id`, `item_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- Outils récolteurs et exigences des nœuds
CREATE TABLE IF NOT EXISTS `wowlheim_tool` (
  `item_id` INT UNSIGNED NOT NULL PRIMARY KEY,
  `kind` VARCHAR(8) NOT NULL COMMENT 'axe | pick',
  `tier` TINYINT UNSIGNED NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
CREATE TABLE IF NOT EXISTS `wowlheim_node` (
  `gameobject_entry` INT UNSIGNED NOT NULL PRIMARY KEY,
  `tool_kind` VARCHAR(8) NOT NULL,
  `min_tier` TINYINT UNSIGNED NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- GameObjects de substitution (modèles existants du client) dans la plage réservée 9100000+.
-- Les vrais modèles viendront d'un patch MPQ en phase 5.
DELETE FROM `gameobject_template` WHERE `entry` BETWEEN 9100001 AND 9100099;
-- 9100001..9100007 : pièces ; les nœuds de ressources (9101001+) sont dans 003_nodes.sql
INSERT INTO `gameobject_template` (`entry`,`type`,`displayId`,`name`,`size`) VALUES
 (9100001, 5, 4651, 'Plancher en bois (proxy)', 2),
 (9100002, 5, 113,  'Mur en bois (proxy)', 2),
 (9100003, 5, 275,  'Toit en bois (proxy)', 2),
 (9100004, 5, 199,  'Poteau en bois (proxy)', 1.5),
 (9100006, 5, 208,  'Établi (proxy)', 1.5),
 (9100007, 5, 679,  'Forge (proxy)', 1.5),
 (9100008, 5, 199,  'Billot de bûcheron (proxy)', 1),
 (9100009, 5, 285,  'Étendoir à peaux (proxy)', 1),
 (9100010, 5, 286,  'Soufflet (proxy)', 1),
 (9100011, 5, 208,  'Enclume (proxy)', 1),
 (9100012, 5, 113,  'Étau (proxy)', 1);
-- Feu de camp : même modèle/données que le feu de camp basique 29784 (type 8)
INSERT INTO `gameobject_template` (`entry`,`type`,`displayId`,`name`,`faction`,`size`,`data0`,`data1`,`data2`)
 SELECT 9100005, `type`, `displayId`, 'Feu de camp (proxy)', `faction`, `size`, `data0`, `data1`, `data2` FROM `gameobject_template` WHERE `entry` = 29784;

INSERT INTO `wowlheim_piece_template` (`id`,`name`,`gameobject_entry`,`material`,`max_health`,`supports`,`requires_workbench`,`kind`,`sx`,`sy`,`sz`,`ext_station`,`ext_distance`,`ext_stack`) VALUES
 (1, 'Plancher', 9100001, 0, 200, 1, 0, 'floor',     2,   2,   0.2, '', 5, 0),
 (2, 'Mur',      9100002, 0, 200, 1, 0, 'wall',      2,   0.2, 2,   '', 5, 0),
 (3, 'Toit',     9100003, 0, 150, 1, 0, 'roof',      2,   2,   0.2, '', 5, 0),
 (4, 'Poteau',   9100004, 0, 250, 1, 0, 'pillar',    0.3, 0.3, 2,   '', 5, 0),
 (5, 'Feu de camp', 9100005, 0, 100, 0, 0, 'fire',   0.8, 0.8, 0.4, '', 5, 0),
 (6, 'Établi',   9100006, 0, 400, 0, 0, 'workbench', 1.5, 0.8, 1,   '', 5, 0),
 (7, 'Forge',    9100007, 0, 400, 0, 1, 'forge',     1.5, 1.0, 1,   '', 5, 0),
 (8, 'Billot de bûcheron', 9100008, 0, 150, 0, 0, 'extension', 0.8, 0.8, 0.8, 'workbench', 5, 0),
 (9, 'Étendoir à peaux',   9100009, 0, 150, 0, 0, 'extension', 1.0, 0.4, 1.2, 'workbench', 5, 0),
 (10, 'Soufflet',          9100010, 0, 150, 0, 0, 'extension', 0.8, 0.8, 0.8, 'forge', 5, 0),
 (11, 'Enclume',           9100011, 0, 200, 0, 0, 'extension', 0.8, 0.5, 0.6, 'forge', 5, 0),
 (12, 'Étau',              9100012, 0, 150, 0, 0, 'extension', 0.8, 0.5, 0.8, 'forge', 5, 0);

-- Coûts : les valeurs des prefabs Unity ne sont pas lisibles dans le DLL (docs/VALHEIM_RULES.md 5) ; valeurs choisies, à équilibrer.
-- 9200001 = Bois, 9200002 = Pierre (voir tools/resources et docs/RESOURCES.md).
INSERT INTO `wowlheim_piece_cost` (`piece_id`,`item_id`,`count`) VALUES
 (1, 9200001, 2),
 (2, 9200001, 2),
 (3, 9200001, 2),
 (4, 9200001, 1),
 (5, 9200001, 5),
 (6, 9200001, 10),
 (7, 9200002, 20),
 (7, 9200013, 5),
 (8, 9200001, 5),
 (8, 9200003, 2),
 (9, 9200001, 8),
 (9, 9200006, 4),
 (10, 9200001, 6),
 (10, 9200006, 6),
 (11, 9200002, 10),
 (11, 9200013, 5),
 (12, 9200001, 4),
 (12, 9200014, 4);

-- Zones interdites supplémentaires (villages et camps de départ, par AreaTable) : à compléter après audit.
DELETE FROM `wowlheim_forbidden_area`;
