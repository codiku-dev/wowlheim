-- Marteau de construction (équiper le marteau ouvre le panneau de construction de l'addon) et kit de départ de tous les personnages :
-- le marteau + 20 Bois (de quoi poser un établi, 10 Bois, dès l'arrivée). Entrée 9201100. Rejouable.
DELETE FROM `item_template` WHERE `entry` = 9201100;
CREATE TEMPORARY TABLE `tmp_hammer` SELECT * FROM `item_template` WHERE `entry` = 9201011;
UPDATE `tmp_hammer` SET `entry` = 9201100, `name` = 'Marteau de construction', `displayid` = 8568, `dmg_min1` = 1, `dmg_max1` = 2,
  `description` = 'Wowlheim - équipez-le pour construire';
INSERT INTO `item_template` SELECT * FROM `tmp_hammer`;
DROP TEMPORARY TABLE `tmp_hammer`;

DELETE FROM `playercreateinfo_item` WHERE `itemid` IN (9201100, 9200001);
INSERT INTO `playercreateinfo_item` (`race`, `class`, `itemid`, `amount`) SELECT `race`, `class`, 9201100, 1 FROM `playercreateinfo`;
INSERT INTO `playercreateinfo_item` (`race`, `class`, `itemid`, `amount`) SELECT `race`, `class`, 9200001, 20 FROM `playercreateinfo`;
