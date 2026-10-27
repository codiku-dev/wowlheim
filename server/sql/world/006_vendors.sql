-- GENERE par tools/resources/generate.py : NE PAS EDITER A LA MAIN. Rejouable (idempotent).
SET NAMES utf8mb4;
-- 006 : AUCUN vendeur de materiaux Wowlheim (Valheim : le marchand Haldor ne vend aucun materiau de construction).
-- Supprime les lignes npc_vendor de la plage Wowlheim (9200001-9299999) ajoutees par l'ancienne version de ce script.
DELETE FROM `npc_vendor` WHERE `item` BETWEEN 9200001 AND 9299999;
