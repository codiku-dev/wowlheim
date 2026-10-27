-- Wowlheim : textes de playerbots appeles par leur cle anglaise (BOT_TEXT2("..."))
-- et absents de ai_playerbot_texts : sans ligne, playerbots affiche la cle en anglais.
-- On ajoute une ligne FR par cle visible des joueurs (guilde, groupe, raid). Base classicmangos_bots uniquement.
-- Rejouable : supprime d'abord les lignes ajoutees (reply_type 0, name = cle).
SET NAMES utf8mb4;
DELETE FROM `ai_playerbot_texts` WHERE `name` IN (
 '%name, I got this guild....', '%name, you should join my guild!',
 '%name, your guild has over 1000 members. To stop it from reaching the 1064 member limit I refuse to join it.',
 '..and it''s really beautifull and I feel like crying...', '..and please stop I''m lonenly and we can get a ride the whole time...',
 '..and watch your dog and do your homework...', '..and we have more members than just me...',
 '..and we raid once a week and are working on MC raids...', 'Haha.. you are the man! We are going to raid Molten...',
 'Hey %name I''m raiding in %zone_name do you want to join me?', 'Hey %name do you want create a guild together?',
 'Hey %name do you want join my group? I''m heading for %zone_name',
 'Hey %name do you want to join %guildname? We have %members members and looking to become number 1 of the server.',
 'Hey %name do you want to join my guild?', 'Hey Hey! do you guys wanna join my gild????',
 'Hey anyone wanna group up in %zone_name?', 'Hey anyone want to raid in %zone_name', 'Hey do you want to form a guild?',
 'Hey man you wanna join my guild %name?', 'I am leaving this guild to prevent it from reaching the %guild_bot_limit member limit.',
 'I think you would be a good contribution to %guildname. Would you like to join %name?', 'I would love to join!',
 'I''m not really good at smalltalk. Do you wanna join my guild %name/r?', 'Joining as %role, %spotsleft %role spots left.',
 'Joining as %role.', 'My guild %guildname has %members quality members. Would you like to make it 1 more %name?',
 'Send me an invite %name!', 'So what do you guys say are you going to join are you going to join?',
 'Sorry, I am in a guild already %name.', 'Sorry, I don''t want to join your guild %name :(.', 'Sounds good %name sign me up!',
 'Sure I will join you.', 'We''ve got a bunch of high levels and we are really super friendly..',
 'Welcome to %zone_name.... do you want to join my guild %name?', 'You are actually going to join my guild %name?',
 'You are not in a guild %name!',
 '|cff00ff00%itemcount items recieved from mail: ', '|cffffff00%money |cff00ff00recieved from mail.');

INSERT INTO `ai_playerbot_texts` (`name`, `text`, `say_type`, `reply_type`, `text_loc1`, `text_loc2`, `text_loc3`, `text_loc4`, `text_loc5`, `text_loc6`, `text_loc7`, `text_loc8`)
SELECT k, fr, 0, 0, '', fr, '', '', '', '', '', '' FROM (
 SELECT '%name, I got this guild....' k, '%name, j''ai une guilde...' fr UNION ALL
 SELECT '%name, you should join my guild!', '%name, tu devrais venir dans ma guilde !' UNION ALL
 SELECT '%name, your guild has over 1000 members. To stop it from reaching the 1064 member limit I refuse to join it.', '%name, ta guilde est deja enorme, je passe mon tour' UNION ALL
 SELECT '..and it''s really beautifull and I feel like crying...', '..et franchement c''est trop beau, j''en pleurerais...' UNION ALL
 SELECT '..and please stop I''m lonenly and we can get a ride the whole time...', '..et allez, chui tout seul, on pourrait jouer ensemble tout le temps...' UNION ALL
 SELECT '..and watch your dog and do your homework...', '..et promener ton chien et faire tes devoirs...' UNION ALL
 SELECT '..and we have more members than just me...', '..et on est plus que moi hein...' UNION ALL
 SELECT '..and we raid once a week and are working on MC raids...', '..et on raid une fois par semaine, on bosse sur le Coeur du Magma...' UNION ALL
 SELECT 'Haha.. you are the man! We are going to raid Molten...', 'haha t''es un chef ! on va raid le Coeur du Magma...' UNION ALL
 SELECT 'Hey %name I''m raiding in %zone_name do you want to join me?', 'salut %name, je raid a %zone_name, tu viens ?' UNION ALL
 SELECT 'Hey %name do you want create a guild together?', 'dis %name, ca te dit qu''on monte une guilde ensemble ?' UNION ALL
 SELECT 'Hey %name do you want join my group? I''m heading for %zone_name', 'salut %name, tu veux grouper ? je pars vers %zone_name' UNION ALL
 SELECT 'Hey %name do you want to join %guildname? We have %members members and looking to become number 1 of the server.', 'salut %name, ca te dit de rejoindre %guildname ? on est %members et on vise le top du serveur' UNION ALL
 SELECT 'Hey %name do you want to join my guild?', 'salut %name, tu veux rejoindre ma guilde ?' UNION ALL
 SELECT 'Hey Hey! do you guys wanna join my gild????', 'yo ! quelqu''un veut rejoindre ma guilde ????' UNION ALL
 SELECT 'Hey anyone wanna group up in %zone_name?', 'quelqu''un pour grouper a %zone_name ?' UNION ALL
 SELECT 'Hey anyone want to raid in %zone_name', 'quelqu''un chaud pour raid a %zone_name ?' UNION ALL
 SELECT 'Hey do you want to form a guild?', 'ca te dit de monter une guilde ?' UNION ALL
 SELECT 'Hey man you wanna join my guild %name?', 'dis %name, tu veux venir dans ma guilde ?' UNION ALL
 SELECT 'I am leaving this guild to prevent it from reaching the %guild_bot_limit member limit.', 'je quitte la guilde, on est trop nombreux' UNION ALL
 SELECT 'I think you would be a good contribution to %guildname. Would you like to join %name?', 'je pense que tu serais un bon ajout pour %guildname, ca te tente %name ?' UNION ALL
 SELECT 'I would love to join!', 'avec plaisir !' UNION ALL
 SELECT 'I''m not really good at smalltalk. Do you wanna join my guild %name/r?', 'chui pas doue pour papoter, mais tu veux venir dans ma guilde %name ?' UNION ALL
 SELECT 'Joining as %role, %spotsleft %role spots left.', 'je viens en %role, il reste %spotsleft places de %role' UNION ALL
 SELECT 'Joining as %role.', 'je viens en %role' UNION ALL
 SELECT 'My guild %guildname has %members quality members. Would you like to make it 1 more %name?', 'ma guilde %guildname a %members membres sympas, ca te dit d''etre le suivant %name ?' UNION ALL
 SELECT 'Send me an invite %name!', 'invite moi %name !' UNION ALL
 SELECT 'So what do you guys say are you going to join are you going to join?', 'alors, vous venez ou pas ?' UNION ALL
 SELECT 'Sorry, I am in a guild already %name.', 'dsl %name, j''ai deja une guilde' UNION ALL
 SELECT 'Sorry, I don''t want to join your guild %name :(.', 'dsl %name, ta guilde me tente pas' UNION ALL
 SELECT 'Sounds good %name sign me up!', 'ca marche %name, compte sur moi !' UNION ALL
 SELECT 'Sure I will join you.', 'ok je viens avec toi' UNION ALL
 SELECT 'We''ve got a bunch of high levels and we are really super friendly..', 'on a plein de hauts niveaux et on est super sympas..' UNION ALL
 SELECT 'Welcome to %zone_name.... do you want to join my guild %name?', 'bienvenue a %zone_name... tu veux rejoindre ma guilde %name ?' UNION ALL
 SELECT 'You are actually going to join my guild %name?', 'tu vas vraiment rejoindre ma guilde %name ?' UNION ALL
 SELECT 'You are not in a guild %name!', 't''es pas dans une guilde %name !' UNION ALL
 SELECT '|cff00ff00%itemcount items recieved from mail: ', '|cff00ff00%itemcount objets recus par courrier : ' UNION ALL
 SELECT '|cffffff00%money |cff00ff00recieved from mail.', '|cffffff00%money |cff00ff00recus par courrier.'
) t;
