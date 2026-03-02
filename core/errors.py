import logging
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from config.config import config
from utils.embeds import create_embed

logger = logging.getLogger(__name__)

# ============================================================
# WEBHOOK LOGGING
# ============================================================


async def log_to_webhook(message: str):
    """Sends a log message to the configured Discord webhook."""
    webhook_url = await config.get_bot_config("webhook_url")
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

# ============================================================
# SLASH COMMAND ERROR HANDLING
# ============================================================


async def handle_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Centralized error handler for all slash commands."""
    if isinstance(error, app_commands.CommandOnCooldown):
        embed = create_embed(
            description=f"⏱ This command is on cooldown. Try again in {error.retry_after:.1f}s"
        )

    elif isinstance(error, app_commands.CommandNotFound):
        logger.warning(
            f"CommandNotFound: {type(error).__name__} - {error}", exc_info=True)
        await log_to_webhook(f"CommandNotFound: `{interaction.command}`:\n{type(error).__name__} - {error}")
        embed = create_embed(
            description=f"❌ This command is not registered. Try restarting your Discord client or wait a few minutes for commands to sync."
        )

    elif isinstance(error, app_commands.BotMissingPermissions):
        embed = create_embed(
            description=f"❌ I don't have the required permissions to do that."
        )

    elif isinstance(error, app_commands.CheckFailure):
        embed = create_embed(
            description=f"❌ You are not allowed to use this command."
        )

    else:
        logger.error(
            f"Unhandled slash command error: {type(error).__name__} - {error}", exc_info=True)
        await log_to_webhook(f"Unhandled slash command error in `{interaction.command}`:\n{type(error).__name__} - {error}")
        embed = create_embed(
            description="❌ An unexpected error occurred. The developers have been notified."
        )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.errors.NotFound:
        logger.warning(
            "Failed to send error response: interaction expired or webhook not found")
    except discord.errors.HTTPException as e:
        logger.error(f"Failed to send error response: {e}")
