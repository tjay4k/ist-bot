import discord
from discord.ext import commands
from pathlib import Path
import logging
import importlib
from config.config import config
from config.defaults import get_all_defaults
from core.errors import handle_app_command_error

logger = logging.getLogger(__name__)

# ============================================================
# BOT CLASS
# ============================================================

class ISTBot(commands.Bot):
    """
    Core bot class.

    Handles:
    • startup configuration
    • service loading
    • cog loading
    • command syncing
    • guild registration
    • runtime mode behavior
    """

    def __init__(self, mode: str = "prod"):
        self.mode = mode.lower()
        self.services = {}

        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

    # ----------------------------
    # SERVICE REGISTRY
    # ----------------------------

    def register_service(self, name: str, service):
        """Register a service. Access anywhere via bot.get_service('name')."""
        self.services[name] = service

    def get_service(self, name: str):
        """Retrieve a registered service by name. Returns None if not found."""
        return self.services.get(name)

    # -------------------------
    # STARTUP LIFECYCLE
    # -------------------------

    async def setup_hook(self):
        """
        Runs before the bot connects to Discord.

        Order of operations:
        1. Enable centralized command error handling
        2. Load services (database, etc)
        3. Initialize config with database
        4. Load cogs
        5. Sync slash commands
        """
        logger.info(f"Starting bot in {self.mode.upper()} mode")

        self.tree.on_error = handle_app_command_error

        await self.load_services()
        config.init(self)

        await self.load_enabled_cogs()
        await self.sync_commands()

    async def on_ready(self):
        """Fires when the bot is fully connected and ready."""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")

        await self.change_presence(
            activity=discord.CustomActivity(name="Assisting High Command ⚙️"),
            status=discord.Status.online
        )

        # ---------- Register existing guilds ----------
        await self.register_guilds()

    # -------------------------
    # SERVICE LOADING
    # -------------------------
    async def load_services(self):
        """
        Auto-discovers and loads all services in the services/ directory.
        Each service must have an async setup(bot) function to be loaded.
        """
        for file in Path("./services").glob("*.py"):
            if file.stem.startswith("_"):
                continue
            module = importlib.import_module(f"services.{file.stem}")
            if hasattr(module, "setup"):
                await module.setup(self)
                logger.info(f"Loaded service: {file.stem}")
    
    # -------------------------
    # COG LOADING
    # -------------------------

    async def load_enabled_cogs(self):
        """
        Auto-discovers and load cogs based on runtime mode.

        core/extensions/ -> always loaded (prod, dev, & debug)
        dev/             -> only loaded in dev/debug mode
        cogs/            -> always loaded (all modes)
        """
        # ---------- Core extensions (all modes) ----------
        for file in Path("./core/extensions").glob("*.py"):
            if file.stem.startswith("_"):
                continue
            ext = f"core.extensions.{file.stem}"
            if ext in self.extensions:
                continue
            try:
                await self.load_extension(f"core.extensions.{file.stem}")
                logger.info(f"Loaded core extension: {file.stem}")
            except Exception as e:
                logger.error(
                    f"Failed to load core extension {file.stem}", exc_info=True)

        # ---------- Dev scripts (dev/debug mode only) ----------
        if self.mode in ("dev", "debug"):
            logger.info("DEV mode: developer tools enabled")
            for file in Path("./dev").glob("*.py"):
                if file.stem.startswith("_"):
                    continue
                ext = f"dev.{file.stem}"
                if ext in self.extensions:
                    continue
                try:
                    await self.load_extension(ext)
                    logger.info(f"Loaded dev cog: {file.stem}")
                except Exception as e:
                    logger.error(
                        f"Failed to load dev cog {file.stem}", exc_info=True)

        # ---------- Cogs (all modes) ----------
        for file in Path("./cogs").glob("*.py"):
            if file.stem.startswith("_"):
                continue
            try:
                await self.load_extension(f"cogs.{file.stem}")
                logger.info(f"Loaded {file.stem}")
            except Exception as e:
                logger.error(f"Failed to load {file.stem}", exc_info=True)

    # -------------------------
    # COMMAND SYNCING
    # -------------------------

    async def sync_commands(self):
        """
        Sync application commands based on runtime mode.

        dev/debug -> sync to dev guilds only (instant)
        prod      -> global sync (can take up to 1 hour)
        """
        try:
            if self.mode in ("dev", "debug"):
                guild_ids = await config.get_dev_guild_ids()

                if not guild_ids:
                    logger.warning("No dev_guild_ids set; skipping guild sync")
                    return

                for guild_id in guild_ids:
                    guild = discord.Object(id=guild_id)
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    logger.info(
                        f"Synced {len(synced)} commands to DEV guild {guild_id}")

            else:
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} commands globally")

        except Exception as e:
            logger.error(
                f"Command sync failed: {type(e).__name__} - {e}", exc_info=True)

    # -------------------------
    # GUILD REGISTRATION
    # -------------------------

    async def register_guild_defaults(self, guild_id: int):
        """Insert default database rows for a new guild."""
        db = self.get_service("db")
        await db.executemany(
            """INSERT INTO action_log_events (guild_id, event_category, event_type)
            VALUES ($1, $2, $3) ON CONFLICT DO NOTHING""",
            get_all_defaults(guild_id)
        )
        logger.debug(f"Inserted default rows for guild {guild_id}")

    async def register_guilds(self):
        """Register all current guilds in the database on startup."""
        db = self.get_service("db")
        for guild in self.guilds:
            await db.execute(
                "INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING",
                guild.id
            )
            await self.register_guild_defaults(guild.id)
        logger.info(f"Registered {len(self.guilds)} guild(s) in database")

    # ----------------------------
    # GUILD EVENTS
    # ----------------------------

    async def on_guild_join(self, guild: discord.Guild):
        """Register guild in database when bot joins a new server."""
        db = self.get_service("db")
        await db.execute(
            "INSERT INTO guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING",
            guild.id
        )
        await self.register_guild_defaults(guild.id)
        logger.debug(f"Registered new guild: {guild.name} ({guild.id})")

    async def on_guild_remove(self, guild: discord.Guild):
        """Remove guild from database when bot leaves."""
        db = self.get_service("db")
        await db.execute(
            "DELETE FROM guilds WHERE guild_id = $1",
            guild.id
        )
        logger.debug(f"Removed guild: {guild.name} ({guild.id})")
