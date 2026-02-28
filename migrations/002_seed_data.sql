-- Bot config
INSERT INTO bot_config (key, value) VALUES
    ('webhook_url', 'https://discord.com/api/webhooks/1474883236650811485/jxJuMe6JoXbzg5cZmGTghm34K73PDzK6KNSmDSTL6-BHBTwzN2A2MGZooxCZuDKSSMFI'),
    ('disable_message_delete_log', 'false'),
    ('disable_message_edit_log', 'false'),
    ('disable_message_bulk_delete_log', 'false');

-- Owners
INSERT INTO bot_owners (discord_id) VALUES
    (433328712532885504);

-- Developers
INSERT INTO bot_developers (discord_id) VALUES
    (777506217551200296);

-- Dev guilds
INSERT INTO dev_guilds (guild_id) VALUES
    (1309981030790463529);

INSERT INTO guilds (guild_id) VALUES
    (1466555681300549816),
    (1473769132141969620),
    (1309981030790463529);

-- Action log events
INSERT INTO action_log_events (guild_id, event_category, event_type, channel_id) VALUES
    (1466555681300549816, 'message_events', 'delete', 1466555684505256054),
    (1466555681300549816, 'message_events', 'edit', 1466555684505256054),
    (1466555681300549816, 'message_events', 'bulk_delete', 1466555684505256054),
    (1473769132141969620, 'message_events', 'delete', 1475271583915573288),
    (1473769132141969620, 'message_events', 'edit', 1475271583915573288),
    (1473769132141969620, 'message_events', 'bulk_delete', 1475271583915573288),
    (1309981030790463529, 'message_events', 'delete', 1477109624879448084),
    (1309981030790463529, 'message_events', 'edit', 1477109624879448084),
    (1309981030790463529, 'message_events', 'bulk_delete', 1477109624879448084);

-- Staff rating
INSERT INTO staff_rating_config (guild_id, auto_post, channel_id, spreadsheet_url, mention_role_id) VALUES
    (1466555681300549816, true, 1466555682714288464, 'https://docs.google.com/spreadsheets/d/1UA9aBymB5Kt5F883k3KE8QR-VfADLsRQV7SfgXVBW0s/edit', 1466555681300549821),
    (1309981030790463529, false, 1474883213749915691, 'https://docs.google.com/spreadsheets/d/1UA9aBymB5Kt5F883k3KE8QR-VfADLsRQV7SfgXVBW0s/edit', NULL);