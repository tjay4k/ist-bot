import discord
from discord.ext import commands
from discord import app_commands, Interaction
import logging
from pathlib import Path
from core.checks import requires_developer, requires_owner
from config.config import config
from utils.embeds import create_embed

logger = logging.getLogger(__name__)

#
# REMOVE await self.bot.tree.sync() EVERYWHERE WHEN REMOVING THESE COMMANDS FROM PROD TO DEV
#

# -------------------------------
# Autocomplete helper(s)
# -------------------------------


def get_all_cogs(bot) -> set[str]:
    all_cogs = [f.stem for f in Path(
        "./cogs").glob("*.py")if not f.name.startswith("_")]
    if bot.mode == "dev":
        all_cogs |= {f.stem for f in Path(
            "./dev").glob("*.py") if not f.stem.startswith("_")}
    return all_cogs


def get_loaded_cogs(bot) -> set[str]:
    return {ext.split(".")[-1] for ext in bot.extensions}


def get_unloaded_cogs(bot) -> set[str]:
    return set(get_all_cogs()) - get_loaded_cogs(bot)


async def loaded_autocomplete(interaction: Interaction, current: str,) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=cog, value=cog)
        for cog in get_loaded_cogs(interaction.client)
        if current.lower() in cog.lower()
    ][:25]


async def unloaded_autocomplete(interaction: Interaction, current: str,) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=cog, value=cog)
        for cog in get_unloaded_cogs(interaction.client)
        if current.lower() in cog.lower()
    ][:25]

# -------------------------------
# Developer cog
# -------------------------------


class DeveloperGroup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_dev_guilds(self) -> list[discord.Object]:
        guild_ids = config.get("general", "dev_guild_ids", default=[])
        if not isinstance(guild_ids, list):
            guild_ids = [guild_ids]
        return [discord.Object(id=gid) for gid in guild_ids]

    async def sync_to_dev_guilds(self):
        for guild in self.get_dev_guilds():
            await self.bot.tree.sync(guild=guild)

    developer = app_commands.Group(
        name="developer", description="Developer commands")
    cog_group = app_commands.Group(
        name="cog", description="Manage cogs", parent=developer)
    config_group = app_commands.Group(
        name="config", description="Manage config", parent=developer)

    # ---------- Cog commands ----------

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

        await self.bot.reload_extension(f"cogs.{cog}")
        await self.sync_to_dev_guilds()
        await self.bot.tree.sync()

        embed = create_embed(description=f"✅ Reloaded '{cog}'")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ---------- Config commands ----------

    @config_group.command(name="reload", description="Reload the config")
    @requires_developer()
    async def reload_config(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config.reload()

        await self.bot.load_enabled_cogs()
        await self.sync_to_dev_guilds()
        await self.bot.tree.sync()

        embed = create_embed(
            description="✅ Reloaded the config and re-sync enabled cogs")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DeveloperGroup(bot))
