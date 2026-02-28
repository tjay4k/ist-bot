import logging

logger = logging.getLogger(__name__)

class Config:
    """Database-backed config with in-memory cache."""

    def __init__(self, path="config.yaml"):
        self._db = None

    def init(self, bot):
        """Called after database service is ready."""
        self._db = bot.get_service("db")

    # -------------------------
    # Bot wide
    # -------------------------

    async def get_owners(self) -> set[int]:
        rows = await self._db.fetch("SELECT discord_id FROM bot_owners")
        return {row["discord_id"] for row in rows}

    async def get_developers(self) -> set[int]:
        rows = await self._db.fetch("SELECT discord_id FROM bot_developers")
        return {row["discord_id"] for row in rows}
    
    async def get_dev_guild_ids(self) -> list[int]:
        rows = await self._db.fetch("SELECT guild_id FROM dev_guilds")
        return [row["guild_id"] for row in rows]
    
    async def get_bot_config(self, key: str, default=None):
        row = await self._db.fetchrow(
            "SELECT value FROM bot_config WHERE key = $1", key)
        return row["value"] if row else default
    
    async def is_cog_globally_enabled(self, cog_name: str) -> bool:
        row = await self._db.fetchrow(
            "SELECT cog_name FROM disabled_cogs_global WHERE cog_name = $1",
            cog_name
        )
        return row is None

    # -------------------------
    # Per guild
    # -------------------------

    async def get_guild_config(self, guild_id: int, key: str, default=None):
        row = await self._db.fetchrow(
            "SELECT value FROM guild_config WHERE guild_id = $1 AND key = $2",
            guild_id, key)
        return row["value"] if row else default

    async def set_guild_config(self, guild_id: int, key: str, value: str):
        await self._db.execute(
            """INSERT INTO guild_config (guild_id, key, value) VALUES ($1, $2, $3)
               ON CONFLICT (guild_id, key) DO UPDATE SET value = $3""",
            guild_id, key, value)

    async def get_action_log_event(self, guild_id: int, event_category: str, event_type: str):
        return await self._db.fetchrow(
            """SELECT enabled, channel_id FROM action_log_events
               WHERE guild_id = $1 AND event_category = $2 AND event_type = $3""",
            guild_id, event_category, event_type)

    async def get_staff_rating_config(self, guild_id: int):
        return await self._db.fetchrow(
            "SELECT * FROM staff_rating_config WHERE guild_id = $1", guild_id)

    async def is_cog_enabled(self, guild_id: int, cog_name: str) -> bool:
        row = await self._db.fetchrow(
            "SELECT enabled FROM guild_cog_config WHERE guild_id = $1 AND cog_name = $2",
            guild_id, cog_name)
        return row is None or row["enabled"]

    async def get_guild_roles(self, guild_id: int, role_type: str) -> set[int]:
        rows = await self._db.fetch(
            "SELECT role_id FROM guild_roles WHERE guild_id = $1 AND role_type = $2",
            guild_id, role_type)
        return {row["role_id"] for row in rows}

# global instance
config = Config()