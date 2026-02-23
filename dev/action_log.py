import discord
from discord.ext import commands
import logging
from config.config import config
from utils.embeds import create_embed

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

    async def get_log_channel(self, guild: discord.Guild, event_config: dict):
        """Resolve the log channel from event config."""
        channel_id = event_config.get("channel_id")
        channel = guild.get_channel(channel_id)
        if not channel:
            logger.warning(
                f"Log channel {channel_id} not found in guild {guild.id}")
        return channel

    async def send_log(self, channel: discord.TextChannel, embed: discord.Embed):
        """Send a log embed with error handling."""
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(
                f"Missing permissions to send to log channel {channel.id} in guild {channel.guild.id}")
        except discord.HTTPException as e:
            logger.error(f"Failed to send log embed: {e}", exc_info=True)

    # -------------------------
    # Message Events
    # -------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author == self.bot.user:
            return

        logger.debug(
            f"on_message_delete fired in guild {message.guild.id} by {message.author.id}")

        event_config = self.get_event_config(
            message.guild.id, "message_events", "delete")
        logger.debug(f"Delete event config: {event_config}")

        if not event_config or not event_config.get("enabled", False):
            logger.debug(
                f"Message delete logging disabled for guild {message.guild.id}")
            return

        channel = await self.get_log_channel(message.guild, event_config)
        if not channel:
            return

        embed = create_embed(
            title="Message Deleted",
            description=(
                f"**Author:** {message.author.mention}\n"
                f"**Channel:** {message.channel.mention}\n"
                f"**Sent:** <t:{int(message.created_at.timestamp())}:R>"
            ),
            color=discord.Color.red(),
            author_name=message.author.name,
            author_icon_url=message.author.avatar.url if message.author.avatar else message.author.default_avatar.url,
            footer=f"User ID: {message.author.id}",
            timestamp=True,
        )
        embed.add_field(
            name="Message:",
            value=message.content or "*No content*",
            inline=False
        )
        await self.send_log(channel, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActionLog(bot))
