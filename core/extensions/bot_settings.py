import discord
from discord.ext import commands
from discord import app_commands, Interaction
import logging
import importlib
from core.checks import requires_owner
from config.config import config
from utils.embeds import create_embed

logger = logging.getLogger(__name__)

# ============================================================
# COG CLASS
# ============================================================


class BotSettings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.get_service("db")
        logger.info("BotSettings cog initialized")

    # -------------------------
    # Command groups
    # -------------------------

    management_group = app_commands.Group(
        name="botsettings", description="Manage bot-wide settings")
    owner_group = app_commands.Group(
        name="owners", description="Manage bot owners", parent=management_group)
    developer_group = app_commands.Group(
        name="developers", description="Manage bot developers", parent=management_group)
    devguild_group = app_commands.Group(
        name="devguilds", description="Manage dev guilds", parent=management_group)

    # -------------------------
    # Owner commands
    # -------------------------

    @owner_group.command(name="add", description="Add a bot owner")
    @requires_owner()
    async def add_owner(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        await self.db.execute(
            "INSERT INTO bot_owners (discord_id) VALUES ($1) ON CONFLICT DO NOTHING",
            user.id
        )
        embed = create_embed(
            description=f"✅ Added {user.mention} as a bot owner")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @owner_group.command(name="remove", description="Remove a bot owner")
    @requires_owner()
    async def remove_owner(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)

        # ---------- Prevent removing last owner ----------
        owners = await config.get_owners()
        if len(owners) <= 1:
            embed = create_embed(
                description="❌ Cannot remove the last bot owner.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        await self.db.execute(
            "DELETE FROM bot_owners WHERE discord_id = $1",
            user.id
        )
        embed = create_embed(
            description=f"✅ Removed {user.mention} as a bot owner")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @owner_group.command(name="list", description="List all bot owners")
    @requires_owner()
    async def list_owners(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        owners = await config.get_owners()
        owner_list = "\n".join(f"<@{owner_id}>" for owner_id in owners)
        embed = create_embed(
            title="Bot Owners",
            description=owner_list or "No owners found",
            color=discord.Color.blurple()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # -------------------------
    # Developer commands
    # -------------------------

    @developer_group.command(name="add", description="Add a bot developer")
    @requires_owner()
    async def add_developer(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        await self.db.execute(
            "INSERT INTO bot_developers (discord_id) VALUES ($1) ON CONFLICT DO NOTHING",
            user.id
        )
        embed = create_embed(
            description=f"✅ Added {user.mention} as a bot developer")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @developer_group.command(name="remove", description="Remove a bot developer")
    @requires_owner()
    async def remove_developer(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        await self.db.execute(
            "DELETE FROM bot_developers WHERE discord_id = $1",
            user.id
        )
        embed = create_embed(
            description=f"✅ Removed {user.mention} as a bot developer")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @developer_group.command(name="list", description="List all bot developers")
    @requires_owner()
    async def list_developers(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        developers = await config.get_developers()
        dev_list = "\n".join(f"<@{dev_id}>" for dev_id in developers)
        embed = create_embed(
            title="Bot Developers",
            description=dev_list or "No developers found",
            color=discord.Color.blurple()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # -------------------------
    # Dev guild commands
    # -------------------------

    @devguild_group.command(name="add", description="Add a dev guild")
    @requires_owner()
    async def add_dev_guild(self, interaction: discord.Interaction, guild_id: str):
        await interaction.response.defer(ephemeral=True)
        await self.db.execute(
            "INSERT INTO dev_guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING",
            int(guild_id)
        )
        embed = create_embed(
            description=f"✅ Added `{guild_id}` as a dev guild")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @devguild_group.command(name="remove", description="Remove a dev guild")
    @requires_owner()
    async def remove_dev_guild(self, interaction: discord.Interaction, guild_id: str):
        await interaction.response.defer(ephemeral=True)
        await self.db.execute(
            "DELETE FROM dev_guilds WHERE guild_id = $1",
            int(guild_id)
        )
        embed = create_embed(
            description=f"✅ Removed `{guild_id}` as a dev guild")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @devguild_group.command(name="list", description="List all dev guilds")
    @requires_owner()
    async def list_dev_guilds(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_ids = await config.get_dev_guild_ids()
        guild_list = "\n".join(f"`{guild_id}`" for guild_id in guild_ids)
        embed = create_embed(
            title="Dev Guilds",
            description=guild_list or "No dev guilds found",
            color=discord.Color.blurple()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # -------------------------
    # Defaults sync command
    # -------------------------

    @management_group.command(name="syncdefaults", description="Reload defaults and sync to all guilds")
    @requires_owner()
    async def sync_defaults(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        import config.defaults as defaults_module
        importlib.reload(defaults_module)

        for guild in self.bot.guilds:
            await self.bot.register_guild_defaults(guild.id)

        embed = create_embed(
            description=f"✅ Reloaded defaults and synced to {len(self.bot.guilds)} guild(s)"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(BotSettings(bot))
