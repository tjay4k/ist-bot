-- ============================================================
-- DEFAULT ACTION LOG EVENTS FOR ALL GUILDS
-- ============================================================

INSERT INTO action_log_events (guild_id, event_category, event_type)
SELECT g.guild_id, e.event_category, e.event_type
FROM guilds g
CROSS JOIN (VALUES
    -- message_events
    ('message_events', 'delete'),
    ('message_events', 'edit'),
    ('message_events', 'bulk_delete'),
    ('message_events', 'image_delete'),
    -- moderation_events
    ('moderation_events', 'ban'),
    ('moderation_events', 'unban'),
    ('moderation_events', 'kick'),
    ('moderation_events', 'timeout'),
    ('moderation_events', 'moderator_commands'),
    -- member_events
    ('member_events', 'join'),
    ('member_events', 'leave'),
    ('member_events', 'nickname_change'),
    ('member_events', 'role_add'),
    ('member_events', 'role_remove'),
    ('member_events', 'invite'),
    -- role_events
    ('role_events', 'create'),
    ('role_events', 'delete'),
    ('role_events', 'update'),
    -- channel_events
    ('channel_events', 'create'),
    ('channel_events', 'update'),
    ('channel_events', 'delete'),
    -- emoji_events
    ('emoji_events', 'create'),
    ('emoji_events', 'name_change'),
    ('emoji_events', 'delete'),
    -- voice_events
    ('voice_events', 'join'),
    ('voice_events', 'leave'),
    ('voice_events', 'move')
) AS e(event_category, event_type)
ON CONFLICT DO NOTHING;