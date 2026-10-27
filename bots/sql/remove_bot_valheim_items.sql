-- Wowlheim : les bots aleatoires (comptes RNDBOT%) jouent a WoW : le contenu Valheim n'existe pas pour eux.
-- Supprime pour leurs personnages TOUS les objets >= 9 000 000 (materiaux, outils, marteau du kit de depart...) :
--   1. character_inventory + item_instance (sacs, banque, equipement ; contenu d'un sac Valheim compris) ;
--   2. mail_items + item_instance (courrier recu par ces personnages ; le courrier lui-meme reste).
-- Rien pour les joueurs reels (autres comptes). Remplace remove_bot_hammer.sql (le marteau 9201100 en fait partie).
-- Base PERSONNAGES ; __REALMD__ = base de connexion (remplacee par bots/server/integrate_main.py, etape sql, apres sauvegarde).
-- Serveur arrete. Rejouable. (En jeu : Wowlheim::PurgeWowlheimItems, connexion + toutes les 30 s, PlayerbotAI.cpp.)
DROP TEMPORARY TABLE IF EXISTS wl_bot_chars;
CREATE TEMPORARY TABLE wl_bot_chars (guid INT UNSIGNED NOT NULL PRIMARY KEY)
  SELECT c.guid AS guid
  FROM characters c
  JOIN __REALMD__.account a ON a.id = c.account
  WHERE a.username LIKE 'RNDBOT%';

-- 1. inventaire (objets Valheim, et tout objet range dans un sac Valheim)
DROP TEMPORARY TABLE IF EXISTS wl_bot_items;
CREATE TEMPORARY TABLE wl_bot_items (item INT UNSIGNED NOT NULL PRIMARY KEY)
  SELECT ci.item AS item
  FROM character_inventory ci
  JOIN wl_bot_chars b ON b.guid = ci.guid
  JOIN item_instance ii ON ii.guid = ci.item
  WHERE ii.itemEntry >= 9000000;
INSERT IGNORE INTO wl_bot_items (item)
  SELECT ci.item
  FROM character_inventory ci
  JOIN wl_bot_chars b ON b.guid = ci.guid
  JOIN item_instance bag ON bag.guid = ci.bag
  WHERE ci.bag <> 0 AND bag.itemEntry >= 9000000;
SELECT COUNT(*) AS objets_valheim_inventaire_bots FROM wl_bot_items;
DELETE ci FROM character_inventory ci JOIN wl_bot_items w ON w.item = ci.item;
DELETE ii FROM item_instance ii JOIN wl_bot_items w ON w.item = ii.guid;

-- 2. courrier recu par les bots
DROP TEMPORARY TABLE IF EXISTS wl_bot_mail_items;
CREATE TEMPORARY TABLE wl_bot_mail_items (item INT UNSIGNED NOT NULL PRIMARY KEY)
  SELECT mi.item_guid AS item
  FROM mail_items mi
  JOIN wl_bot_chars b ON b.guid = mi.receiver
  WHERE mi.item_template >= 9000000;
SELECT COUNT(*) AS objets_valheim_courrier_bots FROM wl_bot_mail_items;
DELETE mi FROM mail_items mi JOIN wl_bot_mail_items w ON w.item = mi.item_guid;
DELETE ii FROM item_instance ii JOIN wl_bot_mail_items w ON w.item = ii.guid;
-- courrier devenu vide d'objets : drapeau has_items remis a 0
UPDATE mail m JOIN wl_bot_chars b ON b.guid = m.receiver
  SET m.has_items = 0
  WHERE m.has_items = 1 AND NOT EXISTS (SELECT 1 FROM mail_items mi WHERE mi.mail_id = m.id);

DROP TEMPORARY TABLE wl_bot_mail_items;
DROP TEMPORARY TABLE wl_bot_items;
DROP TEMPORARY TABLE wl_bot_chars;
