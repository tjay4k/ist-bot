import discord
from discord.ext import commands
import logging
from config.config import config
from core.checks import is_cog_enabled
from utils.embeds import create_embed
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ============================================================
# COG CLASS
# ============================================================


class ActionLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("ActionLog cog initialized")

    # ----------------------------
    # HELPERS
    # ----------------------------

    async def get_log_setup(self, guild: discord.Guild, event_category: str, event_type: str) -> tuple[dict, discord.TextChannel] | tuple[None, None]:
        """Fetch event config and log channel, returns (None, None) if missing, disabled or channel not found."""
        event_config = await config.get_action_log_event(guild.id, event_category, event_type)
        logger.debug(
            f"Event config for {event_type} in guild {guild.id}: {event_config}")

        if not event_config or not event_config["channel_id"]:
            logger.debug(f"{event_type} logging disabled for guild {guild.id}")
            return None, None

        channel_id = event_config["channel_id"]
        channel = guild.get_channel(channel_id)
        if not channel:
            logger.warning(
                f"Log channel {channel_id} not found in guild {guild.id}")
            return None, None

        return event_config, channel

    async def send_log(self, channel: discord.TextChannel, embed: discord.Embed):
        """Send a log embed with error handling."""
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(
                f"Missing permissions to send to log channel {channel.id} in guild {channel.guild.id}")
        except discord.HTTPException as e:
            logger.error(f"Failed to send log embed: {e}", exc_info=True)

    @staticmethod
    def format_account_age(created_at) -> str:
        """Format account age into human readable string."""
        now = datetime.now(timezone.utc)
        delta = now - created_at

        years = delta.days // 365
        months = (delta.days % 365) // 30
        days = (delta.days % 365) % 30

        parts = []
        if years:
            parts.append(f"{years} year{'s' if years != 1 else ''}")
        if months:
            parts.append(f"{months} month{'s' if months != 1 else ''}")
        if days:
            parts.append(f"{days} day{'s' if days != 1 else ''}")

        return ", ".join(parts) or "Today"

    # -------------------------
    # MESSAGE EVENTS
    # -------------------------

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        if not await is_cog_enabled(payload.guild_id, "action_log"):
            return

        message = payload.cached_message
        if message and message.author == self.bot.user:
            return

        logger.debug(
            f"on_raw_message_delete fired in guild {payload.guild_id}")

        _, channel = await self.get_log_setup(guild, "message_events", "delete")
        if not channel:
            return

        # ---------- Build message info ----------
        if message:
            author = message.author
            author_icon = author.display_avatar.url
            msg_channel = message.channel.mention
            sent = f"<t:{int(message.created_at.timestamp())}:R>"
            content = message.content
            author_id = author.id
        else:
            author = None
            author_icon = None
            msg_channel = "*Unknown*"
            sent = "*Unknown*"
            content = "*Message not in cache*"
            author_id = "Unknown"

        embed = create_embed(
            title="Message Deleted",
            description=(
                f"**Author:** {author}\n"
                f"**Channel:** {msg_channel}\n"
                f"**Sent:** {sent}"
            ),
            color=discord.Color.red(),
            author_name=author,
            author_icon=author_icon,
            footer=f"User ID: {author_id} • Message ID: {payload.message_id}",
            timestamp=True,
        )
        embed.add_field(name="Message:", value=content, inline=False)

        await self.send_log(channel, embed)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        if not await is_cog_enabled(payload.guild_id, "action_log"):
            return

        logger.debug(
            f"on_raw_bulk_message_delete fired in guild {payload.guild_id}")

        _, channel = await self.get_log_setup(guild, "message_events", "bulk_delete")
        if not channel:
            return

        # ---------- Build message info ----------
        messages = payload.cached_messages
        message_count = len(messages) if messages else "*Unknown*"

        embed = create_embed(
            title="Bulk Messages Deleted",
            description=(
                f"**Channel:** <#{payload.channel.id}>\n"
                f"*Messages Deleted:** {message_count}"
            ),
            color=discord.Color.red(),
            timestamp=True,
        )

        await self.send_log(channel, embed)

    # ----------------------------
    # MEMBER EVENTS
    # ----------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        logger.debug(
            f"on_member_join fired in guild {member.guild.id} for {member.id}")

        if not await is_cog_enabled(member.guild.id, "action_log"):
            return

        _, channel = await self.get_log_setup(member.guild, "member_events", "join")
        if not channel:
            return

        # ---------- Build member info ----------
        formatted_age = self.format_account_age(member.created_at)

        embed = create_embed(
            title="Member Joined",
            description=(
                f"**User:** {member.mention} ({member.id}\n",
                f"**Account Created:** <t:{int(member.created_at.stimestamp())}:R>\n",
                f"**Account Age:** {formatted_age}"
            ),
            color=discord.Color.green(),
            author_name=member.name,
            author_icon=member.display_avatar.url,
            footer=f"User ID: {member.id}",
            timestamp=True,
        )

        await self.send_log(channel, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActionLog(bot))
