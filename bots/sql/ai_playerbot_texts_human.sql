-- Wowlheim : textes prédéfinis des bots ramenés à ce qu'un vrai joueur écrirait (retour de Robin :
-- « Je viens de looter du bois dur Elwyn » en Général, « jamais un humain ferait ça »).
-- Base classicmangos_bots UNIQUEMENT. Sauvegarde préalable : C:\Wowlheim\bots\backup_ai_playerbot_texts_2.sql
-- Rejouable : chaque groupe (`name`) est vidé puis reconstruit. À jouer après ai_playerbot_texts_casual.sql.
--
-- Attention : playerbots renvoie le NOM de la clé (« suggest_quest ») si un groupe n'a plus aucune ligne,
-- et plante si un reply_type n'en a plus. On ne vide donc jamais un groupe sans le remplir.
-- Les annonces de butin / niveau / quête / mort, suggest_something, suggest_faction, toxiques et les
-- répliques /dire du « custom::say » sont coupées par la CONFIG (bots/server/setup_run.py) : leurs lignes
-- restent en base mais ne sont plus jamais tirées.
--
-- Règles d'écriture : court, familier, sans %my_role / %my_class / %my_race (playerbots y met
-- « protection (0/5/31) warrior » en anglais avec des codes couleur), jamais « LFG » / « LFM » / « WTB »
-- en tête (ces préfixes déclenchent les réponses toutes faites des autres bots).
SET NAMES utf8mb4;

DELETE FROM `ai_playerbot_texts` WHERE `name` IN (
  'suggest_quest', 'suggest_trade', 'suggest_sell', 'suggest_instance',
  'response_lfg_quests_channel', 'response_lfg_quests_channel_in_group',
  'response_lfg_quests_whisper', 'response_lfg_quests_whisper_in_group',
  'response_wtb_items_channel', 'response_wtb_items_whisper',
  'thunderfury_spam', 'hello_follow');

INSERT INTO `ai_playerbot_texts` (`name`, `text`, `say_type`, `reply_type`, `text_loc1`, `text_loc2`, `text_loc3`, `text_loc4`, `text_loc5`, `text_loc6`, `text_loc7`, `text_loc8`)
SELECT n, t, 0, 0, '', t, '', '', '', '', '', '' FROM (
  -- Recherche de groupe pour une quête de son journal (Général / RechercheGroupe, rare)
  SELECT 'suggest_quest' n, 'qq1 pour %quest_link ?' t UNION ALL
  SELECT 'suggest_quest', 'quelqu''un fait %quest_link ? on groupe' UNION ALL
  SELECT 'suggest_quest', 'qqn chaud pour %quest_link ?' UNION ALL
  SELECT 'suggest_quest', 'cherche 1 ou 2 personnes pour %quest_link' UNION ALL
  SELECT 'suggest_quest', '%quest_link qqn ? j''y arrive pas seul' UNION ALL
  SELECT 'suggest_quest', 'quelqu''un sur %quest_link ? mp' UNION ALL
  SELECT 'suggest_quest', 'grp pour %quest_link ?' UNION ALL
  SELECT 'suggest_quest', 'dur en solo %quest_link, qqn veut grouper ?' UNION ALL
  -- Achat occasionnel de composants (%category = lien d'objet)
  SELECT 'suggest_trade', 'ACH %category' UNION ALL
  SELECT 'suggest_trade', 'ach %category, mp' UNION ALL
  SELECT 'suggest_trade', 'qqn vend %category ?' UNION ALL
  SELECT 'suggest_trade', 'quelqu''un aurait %category ? je paye' UNION ALL
  SELECT 'suggest_trade', 'cherche %category, mp moi' UNION ALL
  -- Vente occasionnelle (Commerce en ville, sinon Général)
  SELECT 'suggest_sell', 'VDS %item_formatted_link, mp' UNION ALL
  SELECT 'suggest_sell', 'vds %item_formatted_link' UNION ALL
  SELECT 'suggest_sell', 'VDS %item_formatted_link %cost_gold' UNION ALL
  SELECT 'suggest_sell', 'qqn veut %item_formatted_link ? %cost_gold' UNION ALL
  SELECT 'suggest_sell', 'vends %item_formatted_link, mp si interesse' UNION ALL
  SELECT 'suggest_sell', '%item_formatted_link a vendre, mp' UNION ALL
  SELECT 'suggest_sell', 'VDS %item_formatted_link moins cher que l''HV, mp' UNION ALL
  SELECT 'suggest_sell', 'qui veut %item_formatted_link ? faites une offre' UNION ALL
  -- Donjon (coupé par la config tant que le C++ propose des donjons hors niveau et en anglais)
  SELECT 'suggest_instance', 'qqn pour %instance_name ?' UNION ALL
  SELECT 'suggest_instance', 'LF2M %instance_name' UNION ALL
  SELECT 'suggest_instance', 'LF1M %instance_name' UNION ALL
  SELECT 'suggest_instance', 'grp pour %instance_name ? mp' UNION ALL
  SELECT 'suggest_instance', 'qui est chaud pour %instance_name ?' UNION ALL
  SELECT 'suggest_instance', 'cherche grp %instance_name' UNION ALL
  -- Réponses toutes faites à « LFG [quête] » / « WTB [objet] » d'un joueur (codées en dur, pas de
  -- config pour les couper) : au moins courtes et naturelles.
  SELECT 'response_lfg_quests_channel', 'moi aussi %quest_links' UNION ALL
  SELECT 'response_lfg_quests_channel', '%other_name je l''ai aussi, invite' UNION ALL
  SELECT 'response_lfg_quests_channel', 'pareil, je suis dispo' UNION ALL
  SELECT 'response_lfg_quests_channel_in_group', 'je l''ai aussi mais deja en groupe' UNION ALL
  SELECT 'response_lfg_quests_channel_in_group', 'pareil mais je suis groupé là' UNION ALL
  SELECT 'response_lfg_quests_whisper', 'slt, j''ai aussi %quest_links, on groupe ?' UNION ALL
  SELECT 'response_lfg_quests_whisper', 'moi aussi %quest_links, invite si tu veux' UNION ALL
  SELECT 'response_lfg_quests_whisper', 'yo, je suis dessus aussi, inv' UNION ALL
  SELECT 'response_lfg_quests_whisper', 'j''ai %quest_links aussi, je suis a %zone_name' UNION ALL
  SELECT 'response_lfg_quests_whisper_in_group', 'j''ai %quest_links aussi mais je suis en groupe là' UNION ALL
  SELECT 'response_lfg_quests_whisper_in_group', 'je l''ai aussi mais deja groupé, desole' UNION ALL
  SELECT 'response_wtb_items_channel', '%other_name j''ai %formatted_item_links, mp' UNION ALL
  SELECT 'response_wtb_items_channel', 'j''en ai, mp moi' UNION ALL
  SELECT 'response_wtb_items_whisper', 'slt, j''ai %formatted_item_links si tu cherches tjrs' UNION ALL
  SELECT 'response_wtb_items_whisper', 'j''ai %formatted_item_links, tu proposes combien ?' UNION ALL
  SELECT 'response_wtb_items_whisper', 'tu cherches encore ? j''ai %formatted_item_links' UNION ALL
  -- Le mème d'époque, seulement quand quelqu'un a lié Lame-tonnerre (réponse codée en dur)
  SELECT 'thunderfury_spam', 'quelqu''un a dit %thunderfury_link ?' UNION ALL
  SELECT 'thunderfury_spam', 'qqn a dit %thunderfury_link ?' UNION ALL
  SELECT 'thunderfury_spam', 'Quelqu''un a dit %thunderfury_link ?' UNION ALL
  -- Arrivée dans le groupe d'un joueur (au lieu de « Salut, je te suis ! »)
  SELECT 'hello_follow', 'slt' UNION ALL
  SELECT 'hello_follow', 're' UNION ALL
  SELECT 'hello_follow', 'yo' UNION ALL
  SELECT 'hello_follow', 'salut'
) x;
