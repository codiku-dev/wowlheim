-- GENERE par tools/resources/generate.py : NE PAS EDITER A LA MAIN. Rejouable (idempotent).
SET NAMES utf8mb4;
-- 003 : SUPPRESSION des anciens modeles de noeuds GameObject aux modeles WoW (9101001-9101999) et de leur butin.
-- Remplaces par les arbres, roches, filons (creatures) et ramassables (GameObjects 9130001+) de Valheim, ecrits dans
-- 012_valheim_content.sql (tools/valheim/gen_server_sql.py, positions : C:\Wowlheim\data\wl_terrain\placements.json).
DELETE FROM `gameobject_template` WHERE `entry` BETWEEN 9101001 AND 9101999;
DELETE FROM `gameobject_loot_template` WHERE `entry` BETWEEN 9101001 AND 9101999;
