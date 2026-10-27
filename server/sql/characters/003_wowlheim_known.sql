-- Wowlheim : connaissances du joueur façon Valheim (Player.m_knownMaterial, Player.m_knownStations). Rejouable.
-- server/Wowlheim/Knowledge.cpp ; règles : docs/VALHEIM_RULES.md §10.
CREATE TABLE IF NOT EXISTS `wowlheim_known_item` (
  `guid` INT UNSIGNED NOT NULL COMMENT 'guid du personnage',
  `item` INT UNSIGNED NOT NULL COMMENT 'objet Wowlheim (9200000-9299999) déjà possédé une fois (Player.AddKnownItem)',
  PRIMARY KEY (`guid`, `item`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE IF NOT EXISTS `wowlheim_known_station` (
  `guid` INT UNSIGNED NOT NULL COMMENT 'guid du personnage',
  `kind` VARCHAR(32) NOT NULL COMMENT 'type de station (workbench, forge, stonecutter, artisan)',
  `level` TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'plus haut niveau vu (Player.AddKnownStation : CraftingStation.GetLevel)',
  PRIMARY KEY (`guid`, `kind`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
