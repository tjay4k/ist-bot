import discord
from discord.ext import commands
from discord import app_commands, Interaction
import logging
from pathlib import Path
import importlib
from core.checks import requires_developer, requires_owner
from config.config import config
from utils.embeds import create_embed

logger = logging.getLogger(__name__)

# ============================================================
# AUTOCOMPLETE HELPERS
# ============================================================


def get_all_cogs(bot) -> set[str]:
    """Get all available cog names based on runtime mode."""
    all_cogs = [f.stem for f in Path("./cogs").glob("*.py") if not f.name.startswith("_")]
    if bot.mode in ("dev", "debug"):
        all_cogs |= {f.stem for f in Path("./dev").glob("*.py") if not f.stem.startswith("_")}
    return all_cogs


def get_loaded_cogs(bot) -> set[str]:
    """Get all currently loaded cog names."""
    return {ext.split(".")[-1] for ext in bot.extensions}


def get_unloaded_cogs(bot) -> set[str]:
    """Get all available but unloaded cog names."""
    return set(get_all_cogs(bot)) - get_loaded_cogs(bot)


async def loaded_autocomplete(
    interaction: Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=cog, value=cog)
        for cog in get_loaded_cogs(interaction.client)
        if current.lower() in cog.lower()
    ][:25]


async def unloaded_autocomplete(
    interaction: Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=cog, value=cog)
        for cog in get_unloaded_cogs(interaction.client)
        if current.lower() in cog.lower()
    ][:25]


# ============================================================
# COG CLASS
# ============================================================


class DeveloperGroup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.get_service("db")

    # ----------------------------
    # Helpers
    # ----------------------------

    async def sync_to_dev_guilds(self):
        """Sync commands to all configured dev guilds."""
        guild_ids = await config.get_dev_guild_ids()
        for guild_id in guild_ids:
            try:
                await self.bot.tree.sync(guild=discord.Object(id=guild_id))
            except discord.Forbidden:
                logger.warning(f"Missing access to sync commands to guild {guild_id}")

    # ----------------------------
    # Command groups
    # ----------------------------

    developer = app_commands.Group(name="developer", description="Developer commands")

    cog_group = app_commands.Group(name="cog", description="Manage cogs", parent=developer)

    config_group = app_commands.Group(name="config", description="Manage config", parent=developer)

    service_group = app_commands.Group(name="service", description="Manage services", parent=developer)

    # ----------------------------
    # Cog commands
    # ----------------------------

    @cog_group.command(name="load", description="Load a cog")
    @requires_developer()
    @app_commands.autocomplete(cog=unloaded_autocomplete)
    async def load_cog(self, interaction: discord.Interaction, cog: str):
        await interaction.response.defer(ephemeral=True)

        await self.bot.load_extension(f"cogs.{cog}")
        await self.sync_to_dev_guilds()
        await self.bot.tree.sync()

        embed = create_embed(description=f"✅ Loaded `{cog}`")
        await interaction.followup.send(embed=embed)

    @cog_group.command(name="unload", description="Unload a cog")
    @requires_developer()
    @app_commands.autocomplete(cog=loaded_autocomplete)
    async def unload_cog(self, interaction: discord.Interaction, cog: str):
        await interaction.response.defer(ephemeral=True)

        await self.bot.unload_extension(f"cogs.{cog}")
        await self.sync_to_dev_guilds()
        await self.bot.tree.sync()

        embed = create_embed(description=f"✅ Unloaded '{cog}'")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @cog_group.command(name="reload", description="Reload a cog")
    @requires_developer()
    @app_commands.autocomplete(cog=loaded_autocomplete)
    async def reload_cog(self, interaction: discord.Interaction, cog: str):
        await interaction.response.defer(ephemeral=True)

        full_ext = next((ext for ext in self.bot.extensions if ext.split(".")[-1] == cog), None)
        if not full_ext:
            embed = create_embed(description=f"❌ `{cog}` is not loaded.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        await self.bot.reload_extension(full_ext)
        await self.sync_to_dev_guilds()
        await self.bot.tree.sync()

        embed = create_embed(description=f"✅ Reloaded '{cog}'")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @cog_group.command(name="disable")
    @requires_developer()
    async def disable_cog_global(self, interaction: discord.Interaction, cog: str):
        await interaction.response.defer(ephemeral=True)

        await self.db.execute("INSERT INTO disabled_cogs_global (cog_name) VALUES ($1) ON CONFLICT DO NOTHING", cog)
        embed = create_embed(description=f"✅ Disabled `{cog}` globally")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @cog_group.command(name="enable")
    @requires_developer()
    async def enable_cog_global(self, interaction: discord.Interaction, cog: str):
        await interaction.response.defer(ephemeral=True)

        await self.db.execute("DELETE FROM disabled_cogs_global WHERE cog_name = $1", cog)
        embed = create_embed(description=f"✅ Enabled `{cog}` globally")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ----------------------------
    # Service commands
    # ----------------------------

    @service_group.command(name="reload", description="Reload a service")
    @requires_developer()
    async def reload_service(self, interaction: discord.Interaction, service: str):
        module = importlib.import_module(f"services.{service}")

        # ---------- Close existing service gracefully ----------
        existing = self.bot.get_service(service)
        if existing and hasattr(existing, "close"):
            await existing.close()

        # ---------- Reload and re-setup ----------
        importlib.reload(module)
        if hasattr(module, "setup"):
            await module.setup(self.bot)

    @service_group.command(name="load", description="Load a service")
    @requires_developer()
    async def load_service(self, interaction: discord.Interaction, service: str):
        await interaction.response.defer(ephemeral=True)

        try:
            module = importlib.import_module(f"services.{service}")
            if hasattr(module, "setup"):
                await module.setup(self.bot)

            embed = create_embed(description=f"✅ Loaded service `{service}`")
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Loaded service: {service}")
        except Exception as e:
            embed = create_embed(description=f"❌ Failed to load service `{service}`")
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.error(f"Failed to load service {service}", exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DeveloperGroup(bot))
