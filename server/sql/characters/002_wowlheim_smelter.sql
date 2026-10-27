-- Wowlheim : état des fonderies et fours à charbon posés (Valheim `Smelter`, ZDO de la station). Rejouable.
-- server/Wowlheim/Smelter.cpp ; règles : docs/VALHEIM_RULES.md §9.
CREATE TABLE IF NOT EXISTS `wowlheim_smelter_state` (
  `guid` INT UNSIGNED NOT NULL PRIMARY KEY COMMENT 'guid de la pièce (wowlheim_piece.guid)',
  `fuel` FLOAT NOT NULL DEFAULT 0 COMMENT 'ZDOVars.s_fuel (fractionnaire)',
  `bake` FLOAT NOT NULL DEFAULT 0 COMMENT 'ZDOVars.s_bakeTimer (s)',
  `acc` FLOAT NOT NULL DEFAULT 0 COMMENT 'ZDOVars.s_accTime (s, plafond 3600)',
  `queue` VARCHAR(1024) NOT NULL DEFAULT '' COMMENT 'minerai en file, dans l ordre (ids d objets séparés par des virgules)',
  `output` VARCHAR(1024) NOT NULL DEFAULT '' COMMENT 'produits à récupérer (objet:nombre,...)',
  `updated_at` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'heure unix de la dernière sauvegarde (rattrapage au chargement)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
