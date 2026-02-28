---- BOT WIDE 
CREATE TABLE IF NOT EXISTS bot_owners (
    discord_id BIGINT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS bot_developers (
    discord_id BIGINT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS dev_guilds (
    guild_id BIGINT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS bot_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guilds (
    guild_id BIGINT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS disabled_cogs_global (
    cog_name VARCHAR(100) PRIMARY KEY
);

---- Per guild

-- General guild settings (single values per guild)
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    key VARCHAR(100) NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (guild_id, key)
);

-- Which roles are admin/moderator per guild
CREATE TABLE IF NOT EXISTS guild_roles (
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL,
    role_type VARCHAR(50) NOT NULL,
    PRIMARY KEY (guild_id, role_id, role_type)
);

-- Which cogs are enabled/disabled per guild
CREATE TABLE IF NOT EXISTS guild_cog_config (
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    cog_name VARCHAR(100) NOT NULL,
    enabled BOOLEAN DEFAULT true,
    PRIMARY KEY (guild_id, cog_name)
);

-- Action log events per guild
CREATE TABLE IF NOT EXISTS action_log_events (
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    event_category VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT true,
    channel_id BIGINT,
    PRIMARY KEY (guild_id, event_category, event_type)
);

-- Staff rating config per guild
CREATE TABLE IF NOT EXISTS staff_rating_config (
    guild_id BIGINT PRIMARY KEY REFERENCES guilds(guild_id) ON DELETE CASCADE,
    enabled BOOLEAN DEFAULT true,
    auto_post BOOLEAN DEFAULT false,
    channel_id BIGINT,
    spreadsheet_url TEXT,
    mention_role_id BIGINT
);