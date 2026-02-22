import discord
import logging


logger = logging.getLogger(__name__)


# ---------- REUSABLE EMBED ----------

def create_embed(
        title: str = None,
        description: str = None,
        color: discord.Color | int | tuple = None,
        author_name: str = None,
        author_icon_url: str = None,
        footer: str = None,
        timestamp: bool = False
) -> discord.Embed:
    if isinstance(color, int):
        color = discord.Color(color)
    elif isinstance(color, tuple):
        color = discord.Color.from_rgb(*color)
    elif color is None:
        if description and description.startswith("✅"):
            color = discord.Color.green()
        elif description and description.startswith("❌"):
            color = discord.Color.red()
        else:
            color = discord.Color.blurple()

    embed = discord.Embed(title=title, description=description, color=color)

    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon_url)
    if footer:
        embed.set_footer(text=footer)
    if timestamp:
        embed.timestamp = discord.utils.utcnow()

    return embed
