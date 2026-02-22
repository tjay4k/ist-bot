import discord
import logging


logger = logging.getLogger(__name__)


# ---------- REUSABLE EMBED ----------

def create_embed(
        title: str = None,
        description: str = None,
        color: discord.Color | int | tuple = None
) -> discord.Embed:
    if isinstance(color, int):
        color = discord.Color(color)
    elif isinstance(color, tuple):
        color = discord.Color.from_rgb(*color)
    elif color == None:
        if description and description.startswith("✅"):
            color = discord.Color.green()
        elif description and description.startswith("❌"):
            color = discord.Color.red()
    else:
        color = discord.Color.blurple()

    return discord.Embed(title=title, description=description, color=color)
