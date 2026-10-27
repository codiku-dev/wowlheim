-- GENERE par tools/resources/generate.py : NE PAS EDITER A LA MAIN. Rejouable (idempotent).
SET NAMES utf8mb4;
-- 008 : SUPPRESSION des anciens noeuds de ressources GameObject aux modeles WoW (entrees 9101001-9101999, toutes apparitions).
-- Le monde est desormais peuple d'objets de Valheim (arbres, roches, filons = creatures ; ramassables = GameObjects 9130001+)
-- ecrits dans 012_valheim_content.sql par tools/valheim/gen_server_sql.py, aux positions de C:\Wowlheim\data\wl_terrain\placements.json
-- (tools/resources/place_resources.py, docs/RESOURCES_PLACEMENT.md).
DELETE FROM `gameobject` WHERE `id` BETWEEN 9101001 AND 9101999;
