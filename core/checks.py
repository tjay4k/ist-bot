import discord
from discord import app_commands, Interaction
from discord.ext import commands
from config.config import config

# ============================================================
# COG ACCESS CHECKS
# ============================================================


async def is_cog_enabled(guild_id: int, cog_name: str) -> bool:
    """Check if a cog is enabled both globally and for the specific guild."""
    if not await config.is_cog_globally_enabled(cog_name):
        return False
    return await config.is_cog_enabled(guild_id, cog_name)


# ============================================================
# SLASH COMMAND CHECKS
# ============================================================


def requires_owner():
    """Slash command decorator: only bot owners can run."""
    async def predicate(interaction: Interaction) -> bool:
        owners = await config.get_owners()
        if interaction.user.id in owners:
            return True
        raise app_commands.CheckFailure()
    return app_commands.check(predicate)


def requires_developer():
    """Slash command decorator: bot developers or owners."""
    async def predicate(interaction: Interaction) -> bool:
        owners = await config.get_owners()
        developers = await config.get_developers()
        if interaction.user.id in owners or interaction.user.id in developers:
            return True
        raise app_commands.CheckFailure()
    return app_commands.check(predicate)


def has_manage_bot():
    """Slash command decorator: requires Manage Server permission."""
    async def predicate(interaction: Interaction) -> bool:
        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            raise app_commands.CheckFailure()
        if member.guild_permissions.manage_guild:
            return True
        raise app_commands.CheckFailure()
    return app_commands.check(predicate)


def requires_guild_role(role_type: str):
    """Slash command decorator: user must have a configured guild role."""
    async def predicate(interaction: Interaction) -> bool:
        allowed_role_ids = await config.get_guild_roles(interaction.guild.id, role_type)
        member_role_ids = {role.id for role in interaction.user.roles}
        if allowed_role_ids & member_role_ids:
            return True
        raise app_commands.CheckFailure()
    return app_commands.check(predicate)

# ============================================================
# PREFIX COMMAND CHECKS
# ============================================================


def is_owner_prefix():
    """Prefix command: only bot owners."""
    async def predicate(ctx: commands.Context) -> bool:
        owners = await config.get_owners()
        if ctx.author.id in owners:
            return True
        raise commands.CheckFailure()
    return commands.check(predicate)


def is_developer_prefix():
    """Prefix command: bot developers or owners."""
    async def predicate(ctx: commands.Context) -> bool:
        owners = await config.get_owners()
        developers = await config.get_developers()
        if ctx.author.id in developers or ctx.author.id in owners:
            return True
        raise commands.CheckFailure()
    return commands.check(predicate)
