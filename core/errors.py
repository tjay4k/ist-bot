import logging
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from config.config import config
from utils.embeds import create_embed

# -------------------------------
# UNIVERSAL ERROR HANDLING
#
# This script provides a centralized error handling system for the entire bot.
# -------------------------------

logger = logging.getLogger(__name__)

# ---------- WEBHOOK LOGGING ----------


async def log_to_webhook(message: str):
    """
    Sends a log message to the configured Discord webhook.
    """
    webhook_url = config.get("general", "webhook_url", default=[])
    if not webhook_url:
        logger.warning("No webhook URL configured; skipping webhook log.")
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json={"content": message}) as resp:
                if resp.status != 204:
                    text = await resp.text()
                    logger.warning(f"Webhook response: {resp.status} - {text}")
    except Exception as e:
        logger.error(f"Failed to send webhook log: {type(e).__name__} - {e}")

# ---------- SLASH COMMAND ERROR HANDLING ----------


async def handle_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """
    Handles errors for slash commands.
    """
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = create_embed(
            description=f"⏱ This command is on cooldown. Try again in {error.retry_after:.1f}s"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    elif isinstance(error, app_commands.BotMissingPermissions):
        embed = create_embed(
            description=f"❌ I don't have the required permissions to do that."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    elif isinstance(error, app_commands.CheckFailure):
        embed = create_embed(
            description=f"❌ You are not allowed to use this command."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    else:
        logger.error(
            f"Unhandled slash command error: {type(error).__name__} - {error}", exc_info=True)
        await log_to_webhook(f"Unhandled slash command error in `{interaction.command}`:\n{type(error).__name__} - {error}")
        embed = create_embed(
            description="❌ An unexpected error occurred. The developers have been notified."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
