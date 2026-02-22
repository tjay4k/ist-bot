import discord
from discord import app_commands, Interaction
from discord.ext import commands
from config.config import config

# -------------------------------
# Utility Functions
# -------------------------------


def _raise_check_failure(message: str):
    """Helper to raise an AppCommand CheckFailure with a custom message"""
    raise app_commands.CheckFailure(message)

# -------------------------------
# Slash Command Checks
# -------------------------------


def requires_owner():
    """Slash command decorator: only bot owners can run"""

    owners = set(config.get("general", "owners", default=[]))

    async def predicate(interaction: Interaction) -> bool:
        if interaction.user.id in owners:
            return True
        _raise_check_failure("🚫 Only bot owners can use this command.")
    return app_commands.check(predicate)


def requires_developer():
    """Slash command decorator: bot developers or owners"""

    developers = set(config.get("general", "developers", default=[]))
    owners = set(config.get("general", "owners", default=[]))

    async def predicate(interaction: Interaction) -> bool:
        if interaction.user.id in developers or interaction.user.id in owners:
            return True
        _raise_check_failure("🚫 Only developers can use this command.")
    return app_commands.check(predicate)


def has_manage_bot():
    """Decorator for guild admin commands (Manage Server permission)"""

    async def predicate(interaction: Interaction) -> bool:
        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            _raise_check_failure("Unable to fetch your member data.")

        if member.guild_permissions.manage_guild:
            return True
        _raise_check_failure("❌ You need the Manage Server permission.")
    return app_commands.check(predicate)

# -------------------------------
# Prefix Command Checks
# -------------------------------


def is_owner_prefix():
    """Prefix command: only bot owners"""

    owners = set(config.get("general", "owners", default=[]))

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in owners:
            return True
        raise commands.CheckFailure("🚫 Only bot owners can use this command.")
    return commands.check(predicate)


def is_developer_prefix():
    """Prefix command: bot developers or owners"""

    developers = set(config.get("general", "developers", default=[]))
    owners = set(config.get("general", "owners", default=[]))

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in developers or ctx.author.id in owners:
            return True
        raise commands.CheckFailure("🚫 Only developers can use this command.")
    return commands.check(predicate)
