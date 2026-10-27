-- GENERE par tools/resources/generate.py : NE PAS EDITER A LA MAIN. Rejouable (idempotent).
SET NAMES utf8mb4;
-- 005 : SUPPRESSION des anciens noeuds de validation (Elwynn, Durotar, Dun Morogh ; guid 9500001-9599999) aux modeles WoW.
-- Le DELETE est limite aux entrees de noeuds (9101001-9101999) : les pieces de construction posees dans cette plage
-- de guid (le serveur attribue max(guid)+1) ne sont pas touchees.
DELETE FROM `gameobject` WHERE `guid` BETWEEN 9500001 AND 9599999 AND `id` BETWEEN 9101001 AND 9101999;
