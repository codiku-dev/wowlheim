-- Wowlheim : salutations / au revoir de playerbots trop formels, serviables ou agressifs pour un joueur
-- qui croise un inconnu (retour de Robin : « Bonjour, je peux t'aider ? Il me connait meme pas »).
-- On retire ces lignes et on ajoute des formules courtes et detendues. Base classicmangos_bots uniquement.
SET NAMES utf8mb4;
DELETE FROM `ai_playerbot_texts` WHERE `id` IN (
  878, 880, 881, 882, 884, 887, 888, 889, 890, 891, 892, 893, 894, 895, 896, 897, 898, 899,
  900, 901, 902, 903, 904, 905, 1777, 1778,                                   -- hello
  906, 913, 915, 916, 917, 918, 920, 921, 922, 925, 926, 927, 928, 929, 930,
  931, 932, 933, 934, 1848);                                                  -- goodbye
DELETE FROM `ai_playerbot_texts` WHERE `name` IN ('hello', 'goodbye') AND `text` IN
  ('re', 'slt', 'hey', 'yo', 'salut :)', 'bye', '++', 'a+ !', 'bonne soiree', 'jy vais, a+');
INSERT INTO `ai_playerbot_texts` (`name`, `text`, `say_type`, `reply_type`, `text_loc1`, `text_loc2`, `text_loc3`, `text_loc4`, `text_loc5`, `text_loc6`, `text_loc7`, `text_loc8`)
SELECT n, t, 0, 0, '', t, '', '', '', '', '', '' FROM (
  SELECT 'hello' n, 're' t UNION ALL SELECT 'hello', 'slt' UNION ALL SELECT 'hello', 'hey' UNION ALL
  SELECT 'hello', 'yo' UNION ALL SELECT 'goodbye', 'bye' UNION ALL SELECT 'goodbye', '++' UNION ALL
  SELECT 'goodbye', 'a+ !' UNION ALL SELECT 'goodbye', 'bonne soiree' UNION ALL SELECT 'goodbye', 'jy vais, a+') x;
