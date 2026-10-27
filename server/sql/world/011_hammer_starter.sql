-- Marteau de construction (équiper le marteau ouvre le panneau de construction de l'addon) et kit de départ de tous les personnages.
-- Valheim : on commence avec RIEN d'autre que le marteau ; le premier objectif est l'établi (10 Bois), obtenus en ramassant des
-- branches (Pickable_Branch, sans outil) autour des zones de départ ; la hache en pierre se fabrique ensuite à la main (5 Bois, 4 Pierre).
-- Kit = le marteau seul (les 20 Bois de la version précédente sont retirés). Entrée 9201100. Rejouable.
DELETE FROM `item_template` WHERE `entry` = 9201100;
CREATE TEMPORARY TABLE `tmp_hammer` SELECT * FROM `item_template` WHERE `entry` = 9201011;
UPDATE `tmp_hammer` SET `entry` = 9201100, `name` = 'Marteau de construction', `displayid` = 8568, `dmg_min1` = 1, `dmg_max1` = 2,
  `description` = 'Wowlheim - équipez-le pour construire', `MaxDurability` = 0, `RequiredLevel` = 0;
INSERT INTO `item_template` SELECT * FROM `tmp_hammer`;
DROP TEMPORARY TABLE `tmp_hammer`;

DELETE FROM `playercreateinfo_item` WHERE `itemid` IN (9201100, 9200001);
INSERT INTO `playercreateinfo_item` (`race`, `class`, `itemid`, `amount`) SELECT `race`, `class`, 9201100, 1 FROM `playercreateinfo`;
