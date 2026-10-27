-- Wowlheim : compétences façon Valheim (Skills.Skill : m_level, m_accumulator) par personnage. Rejouable.
-- server/Wowlheim/ValheimSkills.cpp ; règles : docs/VALHEIM_SKILLS.md.
CREATE TABLE IF NOT EXISTS `wowlheim_skill` (
  `guid` INT UNSIGNED NOT NULL COMMENT 'guid du personnage',
  `skill` SMALLINT UNSIGNED NOT NULL COMMENT 'Skills.SkillType : 7 Haches, 12 Pioches, 13 Couper du bois, 107 Fabrication',
  `level` FLOAT NOT NULL DEFAULT 0 COMMENT 'Skill.m_level (0-100, fractionnaire après une perte à la mort)',
  `acc` FLOAT NOT NULL DEFAULT 0 COMMENT 'Skill.m_accumulator (progression vers le niveau suivant)',
  PRIMARY KEY (`guid`, `skill`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
