import discord
from discord.ext import commands
from pathlib import Path
import logging
import importlib
from config.config import config
from core.errors import handle_app_command_error

logger = logging.getLogger(__name__)


class ISTBot(commands.Bot):
    """
    Core bot class.

    Handles:
    • startup configuration
    • cog loading
    • command syncing
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

    # Dynamic service(s) registry/usage

    def register_service(self, name: str, service):
        self.services[name] = service

    def get_service(self, name: str):
        return self._services.get(name)

    # -------------------------
    # Startup lifecycle
    # -------------------------

    async def setup_hook(self):
        """
        Runs before the bot connects to Discord.

        Responsible for:
        • loading cogs
        • syncing slash commands
        • applying mode-specific behavior
        """
        logger.info(f"Starting bot in {self.mode.upper()} mode")

        # Enable centralized error handling
        self.tree.on_error = handle_app_command_error

        await self.load_services()
        # Acces them via: self.bot.get_service("sheets")
        await self.load_enabled_cogs()
        await self.sync_commands()

    async def on_ready(self):
        """Fires when the bot is fully connected."""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")

        await self.change_presence(
            activity=discord.CustomActivity(name="Assisting High Command ⚙️"),
            status=discord.Status.online
        )

    # -------------------------
    # Cog loading
    # -------------------------

    async def load_enabled_cogs(self):
        """
        Auto-discovers cogs and loads those enabled in config.

        DEV mode can optionally include developer tools.
        """
        # ---------- Load core extensions (mode: prod & dev) ----------
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

        # ---------- Load dev/ scripts (mode: dev/debug) ----------
        if self.mode in ("dev", "debug"):
            logger.info("DEV mode: developer tools enabled")
            for file in Path("./dev").glob("*.py"):
                if file.stem.startswith("_"):
                    continue
                ext = f"dev.{file.stem}"
                if ext in self.extensions:
                    continue

                cog = file.stem
                try:
                    await self.load_extension(f"dev.{cog}")
                    logger.info(f"Loaded dev cog: {cog}")
                except Exception as e:
                    logger.error(
                        f"Failed to load dev cog {cog}", exc_info=True)

        # ---------- Load enabled cogs (mode: prod)----------
        try:
            enabled = set(config.get("general", "enabled_cogs", default=[]))
        except KeyError:
            logger.error("enabled_cogs missing from config")
            enabled = set()

        for file in Path("./cogs").glob("*.py"):
            if file.stem.startswith("_"):
                continue

            cog = file.stem

            if cog in enabled:
                try:
                    await self.load_extension(f"cogs.{cog}")
                    logger.info(f"Loaded {cog}")
                except Exception as e:
                    logger.error(f"Failed to load {cog}", exc_info=True)

    # -------------------------
    # Command syncing
    # -------------------------

    async def sync_commands(self):
        """
        Sync application commands based on runtime mode.

        DEV  → sync to test guild only (instant)
        PROD → global sync (can take up to 1 hour)
        DEBUG → guild sync + verbose logging
        """

        try:
            # DEV / DEBUG
            if self.mode in ("dev", "debug"):
                guild_ids = config.get("general", "dev_guild_ids")

                if not guild_ids:
                    logger.warning("No dev_guild_id set; skipping guild sync")
                    return

                if not isinstance(guild_ids, list):
                    guild_ids = [guild_ids]

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
    # Services
    # -------------------------
    async def load_services(self):
        for file in Path("./services").glob("*py"):
            if file.stem.startswith("_"):
                continue
            module = importlib.import_module(f"services.{file.stem}")
            if hasattr(module, "setup"):
                await module.setup(self)
                logger.info(f"Loaded service: {file.stem}")
