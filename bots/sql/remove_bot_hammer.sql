-- Wowlheim : retire le marteau de construction (9201100, kit de depart commun playercreateinfo_item) des personnages
-- des bots aleatoires (comptes RNDBOT%). Rien d'autre : ni les joueurs, ni les autres objets Valheim.
-- Base PERSONNAGES ; __REALMD__ = base de connexion (remplacee par bots/server/integrate_main.py, etape sql, apres sauvegarde).
-- Serveur arrete. Rejouable. (Le module retire aussi le marteau a la connexion des bots : RandomPlayerbotMgr::OnBotLoginInternal.)
DROP TEMPORARY TABLE IF EXISTS wl_bot_hammer;
CREATE TEMPORARY TABLE wl_bot_hammer (item INT UNSIGNED NOT NULL PRIMARY KEY)
  SELECT ci.item AS item
  FROM character_inventory ci
  JOIN item_instance ii ON ii.guid = ci.item
  JOIN characters c ON c.guid = ci.guid
  JOIN __REALMD__.account a ON a.id = c.account
  WHERE ii.itemEntry = 9201100 AND a.username LIKE 'RNDBOT%';
SELECT COUNT(*) AS marteaux_bots_retires FROM wl_bot_hammer;
DELETE ci FROM character_inventory ci JOIN wl_bot_hammer h ON h.item = ci.item;
DELETE ii FROM item_instance ii JOIN wl_bot_hammer h ON h.item = ii.guid WHERE ii.itemEntry = 9201100;
DROP TEMPORARY TABLE wl_bot_hammer;
