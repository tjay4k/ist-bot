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
    
    # ----------------------------
    # Action log commands
    # ----------------------------

    @action_log_group.command(name="setchannel", description="Set the log channel for an action log event")
    @has_manage_bot()
    @app_commands.autocomplete(category=event_category_autocomplete, event=event_type_autocomplete)
    async def set_action_log_channel(
        self,
        interaction: discord.Interaction,
        category: str,
        event: str,
        channel: discord.TextChannel
    ):
        await interaction.response.defer(ephemeral=True)

        await self.db.execute(
            """INSERT INTO action_log_events (guild_id, event_category, event_type, channel_id)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (guild_id, event_category, event_type)
               DO UPDATE SET channel_id = $4""",
            interaction.guild.id, category, event, channel.id
        )

        embed = create_embed(
            description=f"✅ Set `{category} → {event}` log channel to {channel.mention}"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @action_log_group.command(name="clearchannel", description="Clear the log channel for an action log event")
    @has_manage_bot()
    @app_commands.autocomplete(category=event_category_autocomplete, event=event_type_autocomplete)
    async def clear_action_log_channel(
        self,
        interaction: discord.Interaction,
        category: str,
        event: str
    ):
        await interaction.response.defer(ephemeral=True)

        await self.db.execute(
            """UPDATE action_log_events SET channel_id = NULL
               WHERE guild_id = $1 AND event_category = $2 AND event_type = $3""",
            interaction.guild.id, category, event
        )

        embed = create_embed(
            description=f"✅ Cleared log channel for `{category} → {event}`"
        )
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
            embed = create_embed(description="No action log channels configured.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # ---------- Group by category ----------
        categories = {}
        for row in rows:
            cat = row["event_category"]
            if cat not in categories:
                categories[cat] = []
            channel = interaction.guild.get_channel(row["channel_id"]) if row["channel_id"] else None
            categories[cat].append(f"`{row['event_type']}` → {channel.mention if channel else '*Not set*'}")

        embed = create_embed(title="Action Log Settings", color=discord.Color.blurple())
        for cat, events in categories.items():
            embed.add_field(name=cat, value="\n".join(events), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
