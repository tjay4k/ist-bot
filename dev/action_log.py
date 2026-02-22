import discord
from discord.ext import commands
import logging
from config.config import config
from utils.embeds import create_embed

logger = logging.getLogger(__name__)


class ActionLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Message Events ----------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        event_config = config.get("action_log", str(
            message.guild.id), "message_events", "delete")
        if not event_config or not event_config.get("enabled", False):
            return

        channel = message.guild.get_channel(event_config.get("channel_id"))
        if not channel:
            return

        embed = create_embed(
            title="Message Deleted",
            description=f"**Author:** {message.author.mention} ({message.author.id})\n"
            f"**Channel:** [{message.channel.name}](https://discord.com/channels/{message.guild.id}/{message.channel.id})\n"
            f"**Sent:** <t:{int(message.created_at.timestamp())}:R>",
            color=discord.Color.red(),
            author_name=f"{message.author.name}",
            author_icon_url=message.author.avatar.url if message.author.avatar else message.author.default_avatar.url,
            footer=f"ID: {message.author.id}",
            timestamp=True,
        )
        embed.add_field(
            name="**Message**",
            value=message.content,
            inline=False
        )

        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActionLog(bot))
