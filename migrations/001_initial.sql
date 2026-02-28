-- ============================================================
-- INITIAL SCHEMA
-- ============================================================

-- -------------------------
-- Bot wide
-- ------------------------

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

CREATE TABLE IF NOT EXISTS disabled_cogs_global (
    cog_name VARCHAR(100) PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS guilds (
    guild_id BIGINT PRIMARY KEY
);


-- -------------------------
-- Per guild
-- -------------------------

CREATE TABLE IF NOT EXISTS guild_config (
    guild_id BIGINT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    key VARCHAR(100) NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (guild_id, key)
);

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
    channel_id BIGINT,
    PRIMARY KEY (guild_id, event_category, event_type)
);
