import discord
from discord.ext import commands
import logging
from config.config import config
from utils.embeds import create_embed
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ActionLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("ActionLog cog initialized")

    # -------------------------
    # Helpers
    # -------------------------

    def get_event_config(self, guild_id: int, *keys):
        """Fetch event config for a guild and event type."""
        return config.get("action_log", str(guild_id), *keys)

    async def get_log_setup(self, guild: discord.Guild, *keys) -> tuple[dict, discord.TextChannel] | tuple[None, None]:
        """Fetch event config and log channel, returns (None, None) if missing, disabled or channel not found."""
        event_config = self.get_event_config(guild.id, *keys)
        logger.debug(
            f"Event config for {keys[-1]} in guild {guild.id}: {event_config}")

        if not event_config or not event_config.get("enabled", False):
            logger.debug(f"{keys[-1]} logging disabled for guild {guild.id}")
            return None, None

        channel_id = event_config.get("channel_id")
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

    def format_account_age(created_at) -> str:
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
    # Message Events
    # -------------------------

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        # Skip if it isn't a guild message
        if not payload.guild_id:
            return

        # Skip if it can't get the guild object
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        # Skip if author is the bot
        message = payload.cached_message
        if message and message.author == self.bot.user:
            return

        logger.debug(
            f"on_raw_message_delete fired in guild {payload.guild_id}")

        # Skip if disabled & skip if channel is None
        event_config, channel = await self.get_log_setup(guild, "message_events", "delete")
        if not channel:
            return

        # Use cached message if available, otherwise fall back to partial info
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

        # Create embed
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
        embed.add_field(
            name="Message:",
            value=content,
            inline=False
        )
        # Send embed
        await self.send_log(channel, embed)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        # Skip if it isn't a guild message
        if not payload.guild_id:
            return

        # Skip if it can't get the guild object
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        logger.debug(
            f"on_raw_bulk_message_delete fired in guild {payload.guild_id}")

        # Skip if disabled & skip if channel is None
        event_config, channel = await self.get_log_setup(guild, "message_events", "bulk_delete")
        if not channel:
            return

        messages = payload.cached_messages
        if messages:
            message_count = len(messages)
        else:
            message_count = "*Unknown*"

        # WIP

    # -------------------------
    # Member Events
    # -------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        logger.debug(
            f"on_member_join fired in guild {member.guild.id} for {member.id}")

        # Skip if disabled & skip if channel is None
        event_config, channel = await self.get_log_setup(member.guild, "member_events", "join")
        if not channel:
            return

        logger.debug(
            f"on_member_join fired in guild {member.guild.id} for {member.id}")

        account_age = member.created_at
        formatted = self.format_account_age(account_age)

        # Create embed
        embed = create_embed(
            title="Member Joined",
            description=(
                f"**User:** {member.mention} ({member.id}"
            ),
            color=discord.Color.green(),
            author_name=member.name,
            author_icon=member.display_avatar.url,
            footer=f"User ID: {member.id}",
            timestamp=True,
        )
        embed.add_field(
            name="Account Age:",
            value=formatted,
            inline=False
        )
        # Send embed
        await self.send_log(channel, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActionLog(bot))
