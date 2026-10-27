-- Wowlheim : outils, exigences des nœuds et recettes. Rejouable. (Fichier écrit à la main ; réduit le 2026-10-26.)
-- Fidélité à Valheim : les outils et les recettes de la première version (hache/pic d'argent, pic de métal noir aux faux ingrédients,
-- conversions bois précieux / bois robuste / silex / bouts de cuir / toile de lin à l'établi) n'existaient pas dans Valheim : supprimés.
--   * outils (wowlheim_tool : palier, dégâts, durabilité de Valheim) et TOUTES les recettes (Recipe_* de Valheim réalisables ici,
--     station et niveau de station de Valheim) : générés dans 012_valheim_content.sql par tools/valheim/gen_server_sql.py ;
--   * wowlheim_node : vide. Les anciens nœuds GameObject (9101001+) sont supprimés (003/005/008) ; arbres, roches et filons sont des
--     créatures (palier d'outil : wowlheim_tree), les ramassables de Valheim (9130001+) se prennent sans outil.
DELETE FROM `wowlheim_tool`; DELETE FROM `wowlheim_node`; DELETE FROM `wowlheim_recipe_ingredient`; DELETE FROM `wowlheim_recipe`;
