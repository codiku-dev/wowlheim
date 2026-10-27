-- Wowlheim : coffres, portes et lits posés (Valheim `Container`, `Door`, `Bed`). Rejouable.
-- server/Wowlheim/Pieces.cpp ; règles : docs/VALHEIM_RULES.md §14 ; valeurs par pièce : classicmangos.wowlheim_piece_use (012).
CREATE TABLE IF NOT EXISTS `wowlheim_container` (
  `guid` INT UNSIGNED NOT NULL COMMENT 'guid de la pièce (wowlheim_piece.guid)',
  `slot` SMALLINT UNSIGNED NOT NULL COMMENT 'case : 0 .. m_width x m_height - 1, de gauche à droite puis de haut en bas',
  `item_id` INT UNSIGNED NOT NULL,
  `count` INT UNSIGNED NOT NULL DEFAULT 1,
  `durability` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'durabilité de l objet (outils), 0 sinon',
  `random_property` INT NOT NULL DEFAULT 0 COMMENT 'ITEM_FIELD_RANDOM_PROPERTIES_ID',
  `bound` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'objet lié',
  PRIMARY KEY (`guid`, `slot`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='contenu des coffres posés (Container.m_inventory)';

CREATE TABLE IF NOT EXISTS `wowlheim_piece_state` (
  `guid` INT UNSIGNED NOT NULL PRIMARY KEY COMMENT 'guid de la pièce (wowlheim_piece.guid)',
  `door_state` TINYINT NOT NULL DEFAULT 0 COMMENT 'Door : ZDOVars.s_state (0 fermée, 1 / -1 ouverte)',
  `bed_owner` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Bed : ZDOVars.s_owner (guid du personnage)',
  `bed_owner_name` VARCHAR(12) NOT NULL DEFAULT '' COMMENT 'Bed : ZDOVars.s_ownerName'
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='état des portes et des lits posés';

-- Marteau : il n'avait pas de durabilité (MaxDurability 0) ; 012 lui donne celle de Valheim (m_maxDurability 100). Les marteaux
-- déjà possédés ont une durabilité enregistrée de 0, qui les rendrait « cassés » : remis à 100, une seule fois.
CREATE TABLE IF NOT EXISTS `wowlheim_migration` (
  `name` VARCHAR(64) NOT NULL PRIMARY KEY,
  `applied_at` DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='migrations ponctuelles de Wowlheim (déjà appliquées)';
UPDATE `item_instance` SET `durability` = 100
  WHERE `itemEntry` = 9201100 AND `durability` = 0
    AND NOT EXISTS (SELECT 1 FROM `wowlheim_migration` WHERE `name` = 'hammer_durability_100');
INSERT IGNORE INTO `wowlheim_migration` (`name`, `applied_at`) VALUES ('hammer_durability_100', NOW());
