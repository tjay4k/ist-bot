-- ============================================================
-- MEMBER CACHE
-- ============================================================

-- Member cache (current state)
CREATE TABLE IF NOT EXISTS guild_members (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    username TEXT NOT NULL,
    nickname TEXT,
    joined_at TIMESTAMP WITH TIME ZONE,
    account_created_at TIMESTAMP WITH TIME ZONE,
    is_bot BOOLEAN DEFAULT false,
    cached_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id)
);

-- Member roles (current roles)
CREATE TABLE IF NOT EXISTS member_roles (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    role_name TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id, role_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_guild_members_user_id ON guild_members(user_id);
CREATE INDEX IF NOT EXISTS idx_member_roles_guild_user ON member_roles(guild_id, user_id);