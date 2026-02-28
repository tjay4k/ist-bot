# ============================================================
# DEFAULT DATABASE ROWS
#
# This file defines default rows to be inserted into the database
# when the bot joins a new guild, or when /developer syncdefaults is run.
#
# To add new defaults:
# 1. Add the new rows to the relevant function
# 2. Run /developer syncdefaults — no restart needed
# ============================================================


def get_action_log_defaults(guild_id: int) -> list[tuple]:
    """Default action log event rows for a guild."""
    return [
        # ---------- Message events ----------
        (guild_id, "message_events", "delete"),
        (guild_id, "message_events", "edit"),
        (guild_id, "message_events", "bulk_delete"),
        (guild_id, "message_events", "image_delete"),

        # ---------- Moderation events ----------
        (guild_id, "moderation_events", "ban"),
        (guild_id, "moderation_events", "unban"),
        (guild_id, "moderation_events", "kick"),
        (guild_id, "moderation_events", "timeout"),
        (guild_id, "moderation_events", "moderator_commands"),

        # ---------- Member events ----------
        (guild_id, "member_events", "join"),
        (guild_id, "member_events", "leave"),
        (guild_id, "member_events", "nickname_change"),
        (guild_id, "member_events", "role_add"),
        (guild_id, "member_events", "role_remove"),
        (guild_id, "member_events", "invite"),

        # ---------- Role events ----------
        (guild_id, "role_events", "create"),
        (guild_id, "role_events", "delete"),
        (guild_id, "role_events", "update"),

        # ---------- Channel events ----------
        (guild_id, "channel_events", "create"),
        (guild_id, "channel_events", "delete"),
        (guild_id, "channel_events", "update"),

        # ---------- Emoji events ----------
        (guild_id, "emoji_events", "create"),
        (guild_id, "emoji_events", "name_change"),
        (guild_id, "emoji_events", "delete"),

        # ---------- Voice events ----------
        (guild_id, "voice_events", "join"),
        (guild_id, "voice_events", "leave"),
        (guild_id, "voice_events", "move"),
    ]


def get_all_defaults(guild_id: int) -> list[tuple]:
    """
    Aggregate all defaults for a guild.
    Add new feature defaults here as the bot grows.
    """
    return [
        *get_action_log_defaults(guild_id),
    ]