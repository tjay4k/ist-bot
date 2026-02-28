import discord
from discord.ext import commands
from discord import app_commands, Interaction
import logging
from core.checks import requires_owner, has_manage_bot
from config.config import config
from utils.embeds import create_embed

logger = logging.getLogger(__name__)

# ============================================================
# AUTOCOMPLETE HELPERS
# ============================================================


async def event_category_autocomplete(interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
    db = interaction.client.get_service("db")
    rows = await db.fetch(
        "SELECT DISTINCT event_category FROM action_log_events WHERE guild_id = $1",
        interaction.guild.id
    )
    return [
        app_commands.Choice(
            name=row["event_category"], value=row["event_category"])
        for row in rows
        if current.lower() in row["event_category"].lower()
    ]


async def event_type_autocomplete(interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
    db = interaction.client.get_service("db")
    category = interaction.namespace.category
    rows = await db.fetch(
        "SELECT event_type FROM action_log_events WHERE guild_id = $1 AND event_category = $2",
        interaction.guild.id, category
    )
    return [
        app_commands.Choice(name=row["event_type"], value=row["event_type"])
        for row in rows
        if current.lower() in row["event_type"].lower()
    ]


async def cog_autocomplete(self, interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete for loaded cogs."""
    loaded = {ext.split(".")[-1] for ext in interaction.client.extensions}
    return [
        app_commands.Choice(name=cog, value=cog)
        for cog in loaded
        if current.lower() in cog.lower()
    ][:25]

# ============================================================
# COG CLASS
# ============================================================


class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.get_service("db")
        logger.info("Settings cog initialized")

    # ----------------------------
    # Command groups
    # ----------------------------

    settings = app_commands.Group(
        name="settings", description="Manage bot settings")
    action_log_group = app_commands.Group(
        name="actionlog", description="Manage action log settings", parent=settings)
    module_group = app_commands.Group(
        name="module", description="Manage modules", parent=settings
    )

    # ----------------------------
    # Action log commands
    # ----------------------------

    @action_log_group.command(name="channel", description="Set or clear the log channel for an action log event")
    @has_manage_bot()
    @app_commands.autocomplete(category=event_category_autocomplete, event=event_type_autocomplete)
    async def set_action_log_channel(
        self,
        interaction: discord.Interaction,
        category: str,
        event: str,
        channel: discord.TextChannel = None
    ):
        await interaction.response.defer(ephemeral=True)

        await self.db.execute(
            """INSERT INTO action_log_events (guild_id, event_category, event_type, channel_id)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (guild_id, event_category, event_type)
               DO UPDATE SET channel_id = $4""",
            interaction.guild.id, category, event, channel.id if channel else None
        )
        if channel:
            embed = create_embed(
                description=f"✅ Set `{category} → {event}` log channel to {channel.mention}")
        else:
            embed = create_embed(
                description=f"✅ Cleared log channel for `{category} → {event}`")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @action_log_group.command(name="view", description="View current action log settings")
    @has_manage_bot()
    async def view_action_log(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        rows = await self.db.fetch(
            "SELECT event_category, event_type, channel_id FROM action_log_events WHERE guild_id = $1 ORDER BY event_category, event_type",
            interaction.guild.id
        )

        if not rows:
            embed = create_embed(
                description="No action log channels configured.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # ---------- Group by category ----------
        categories = {}
        for row in rows:
            cat = row["event_category"]
            if cat not in categories:
                categories[cat] = []
            channel = interaction.guild.get_channel(
                row["channel_id"]) if row["channel_id"] else None
            categories[cat].append(
                f"`{row['event_type']}` → {channel.mention if channel else '*Not set*'}")

        embed = create_embed(title="Action Log Settings",
                             color=discord.Color.blurple())
        for cat, events in categories.items():
            embed.add_field(name=cat, value="\n".join(events), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ----------------------------
    # Cog management commands
    # ----------------------------
    @module_group.command(name="enable", description="Enable a module for this server")
    @has_manage_bot()
    @app_commands.autocomplete(cog=cog_autocomplete)
    async def enable_cog(self, interaction: discord.Interaction, cog: str):
        await interaction.response.defer(ephemeral=True)
        await self.db.execute(
            """INSERT INTO guild_cog_config (guild_id, cog_name, enabled)
            VALUES ($1, $2, true)
            ON CONFLICT (guild_id, cog_name) DO UPDATE SET enabled = true""",
            interaction.guild.id, cog
        )
        embed = create_embed(description=f"✅ Enabled `{cog}` for this server")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @module_group.command(name="disable", description="Disable a module for this server")
    @has_manage_bot()
    @app_commands.autocomplete(cog=cog_autocomplete)
    async def disable_cog(self, interaction: discord.Interaction, cog: str):
        await interaction.response.defer(ephemeral=True)
        await self.db.execute(
            """INSERT INTO guild_cog_config (guild_id, cog_name, enabled)
            VALUES ($1, $2, false)
            ON CONFLICT (guild_id, cog_name) DO UPDATE SET enabled = false""",
            interaction.guild.id, cog
        )
        embed = create_embed(description=f"✅ Disabled `{cog}` for this server")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @module_group.command(name="list", description="View module status for this server")
    @has_manage_bot()
    async def list_cogs(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        loaded = {ext.split(".")[-1] for ext in interaction.client.extensions}
        rows = await self.db.fetch(
            "SELECT cog_name, enabled FROM guild_cog_config WHERE guild_id = $1",
            interaction.guild.id
        )
        disabled = {row["cog_name"] for row in rows if not row["enabled"]}

        cog_list = "\n".join(
            f"{'✅' if cog not in disabled else '❌'} `{cog}`"
            for cog in sorted(loaded)
        )

        embed = create_embed(
            title="Cog Status",
            description=cog_list or "No Modules enabled",
            color=discord.Color.blurple()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
