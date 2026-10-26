-- Wowlheim : pièces posées (base characters). Rejouable.
CREATE TABLE IF NOT EXISTS `wowlheim_piece` (
  `guid` INT UNSIGNED NOT NULL PRIMARY KEY COMMENT 'guid statique du GameObject (table gameobject)',
  `piece_id` INT UNSIGNED NOT NULL,
  `owner_guid` INT UNSIGNED NOT NULL,
  `map` SMALLINT UNSIGNED NOT NULL,
  `x` FLOAT NOT NULL, `y` FLOAT NOT NULL, `z` FLOAT NOT NULL, `o` FLOAT NOT NULL,
  `health` INT UNSIGNED NOT NULL,
  `placed_at` DATETIME NOT NULL,
  KEY `idx_owner` (`owner_guid`),
  KEY `idx_map` (`map`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
