import discord
from discord.ext import commands
from discord import app_commands
import io
from datetime import datetime, timezone
import logging
import matplotlib.pyplot as plt
from core.checks import requires_developer

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

MAIN_GROUP = 561225773
MAIN_DIVISIONS = [1089454647, 535919754]
SUB_DIVISIONS = [1027815085]
MIN_DISCORD_AGE_DAYS = 0  # Minimum Discord account age in days
MIN_BADGE_COUNT = 0  # Minimum Roblox badge count

# ============================================================
# HELPER FUNCTIONS
# ============================================================


async def report_error(
    interaction: discord.Interaction | None, message: str, level: str = "error", user_message: str | None = None
):
    """Unified error/warning reporter."""
    if level.lower() == "warning":
        logger.warning(message)
    elif level.lower() == "info":
        logger.info(message)
    else:
        logger.error(message)

    # Optional: Add webhook error reporting here if needed
    # if ERROR_WEBHOOK_URL:
    #     async with aiohttp.ClientSession() as session:
    #         try:
    #             await session.post(ERROR_WEBHOOK_URL, json={"content": f"⚠️ {level.upper()}: {message}"})
    #         except Exception as e:
    #             logger.error(f"Failed to send error webhook: {e}")

    if interaction:
        try:
            msg = user_message or "⚠️ An error has occurred, please try again."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.edit_original_response(content=msg)
        except Exception as e:
            logger.error(f"Failed to send ephemeral error message: {e}")


async def fetch_discord_user_info(bot: discord.Client, discord_id: int, interaction: discord.Interaction | None = None):
    """Fetch Discord user information."""
    try:
        user: discord.User = await bot.fetch_user(discord_id)
        account_age_days = (discord.utils.utcnow() - user.created_at).days
        return {
            "id": user.id,
            "username": f"{user.name}#{user.discriminator}" if user.discriminator != "0" else user.name,
            "account_age_days": account_age_days,
            "bot": user.bot,
            "avatar_url": str(user.avatar.url) if user.avatar else None,
            "created_at": user.created_at,
        }
    except discord.NotFound:
        await report_error(
            interaction,
            f"Discord user with ID {discord_id} not found.",
            user_message=f"❌ Discord user with ID **{discord_id}** was not found.",
            level="error",
        )
        return None
    except discord.HTTPException as e:
        await report_error(interaction, f"HTTP error fetching Discord user {discord_id}: {e}", level="error")
        return None


async def generate_badge_growth_graph(
    badges, account_created_date, username, user_id, interaction: discord.Interaction | None = None
):
    """Generate a badge growth graph."""
    if not badges:
        await report_error(interaction, f"No badges to generate graph for {username} ({user_id}).", level="warning")
        return None

    valid_badges = [b for b in badges if b["creation_date"] > account_created_date]
    if not valid_badges:
        await report_error(
            interaction,
            f"No valid badges after filtering by account creation for {username} ({user_id}).",
            level="warning",
        )
        return None

    valid_badges.sort(key=lambda x: x["creation_date"])
    dates = [account_created_date] + [b["creation_date"] for b in valid_badges]
    cumulative = [0] + list(range(1, len(valid_badges) + 1))

    try:
        plt.figure(figsize=(10, 5))
        plt.step(dates, cumulative, where="post", color="green")
        plt.xlabel("Date")
        plt.ylabel("Cumulative Badges")
        plt.title(f"{username} ({user_id}) Badge Growth")
        plt.xticks(rotation=45)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        await report_error(interaction, f"Error generating badge graph for {username} ({user_id}): {e}", level="error")
        return None


def categorize_groups(groups: list[dict]) -> dict:
    """Categorize groups into main divisions, sub divisions, and main group."""
    main_divisions = []
    sub_divisions = []
    main_group = None
    all_groups = []

    for group in groups:
        group_id = group["id"]
        group_name = group["name"]
        role_name = group["role"]

        # Add to all groups list with link
        group_link = f"https://www.roblox.com/groups/{group_id}"
        all_groups.append({"name": group_name, "link": group_link, "role": role_name, "id": group_id})

        # Categorize
        if group_id in MAIN_DIVISIONS:
            main_divisions.append((group_name, role_name, group_link))

        if group_id in SUB_DIVISIONS:
            sub_divisions.append((group_name, role_name, group_link))

        if group_id == MAIN_GROUP:
            main_group = (group_name, role_name, group_link)

    return {
        "main_divisions": main_divisions,
        "sub_divisions": sub_divisions,
        "main_group": main_group,
        "all_groups": all_groups,
    }


def create_roblox_embed(user_data: dict, total_groups: int) -> discord.Embed:
    """Create Roblox information embed."""
    embed = discord.Embed(
        title="• Roblox Account Information •",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc),
    )

    display_name = user_data.get("display_name", user_data["username"])

    # Top row - Identity
    embed.add_field(name="Display Name", value=f"{display_name}", inline=True)
    embed.add_field(name="Username", value=user_data["username"], inline=True)
    embed.add_field(name="User ID", value=f"`{user_data['user_id']}`", inline=True)

    # Second row - Account info
    premium_status = "✅" if user_data.get("has_premium") else "❌"
    banned_status = "✅" if user_data["is_banned"] else "❌"

    embed.add_field(name="Status", value=f"Premium: {premium_status}\nBanned: {banned_status}", inline=True)
    embed.add_field(name="Account Age", value=f"{user_data['account_age_days']} days", inline=True)
    embed.add_field(name="Created At", value=f"<t:{int(user_data['account_created_date'].timestamp())}:F>", inline=True)

    # Third row - Social
    embed.add_field(
        name="Social",
        value=(
            f"Followers: {user_data['followers']}\n"
            f"Following: {user_data['following']}\n"
            f"Friends: {user_data['friends']}"
        ),
        inline=True,
    )
    embed.add_field(
        name="Badges",
        value=(f"Count: {user_data['badge_count']:,}\n" f"Pages: {user_data['badge_pages']}"),
        inline=True,
    )
    embed.add_field(name="Groups", value=f"Count: {total_groups}", inline=True)

    # Fourth row - Link
    embed.add_field(
        name="Profile Link",
        value=f"[View on Roblox](https://www.roblox.com/users/{user_data['user_id']}/profile)",
        inline=True,
    )

    # Previous usernames (if any)
    previous_usernames = user_data.get("previous_usernames", [])
    if previous_usernames:
        # Limit to 10 most recent previous usernames to avoid hitting field limits
        display_usernames = previous_usernames[:10]
        username_text = ", ".join([f"`{name}`" for name in display_usernames])

        # Add "and X more" if there are more than 10
        if len(previous_usernames) > 10:
            username_text += f" and {len(previous_usernames) - 10} more"

        embed.add_field(name="📜 Previous Usernames", value=username_text, inline=False)

    return embed


def create_groups_embed(group_info: dict, user_id: int, total_groups: int) -> discord.Embed:
    """Create a summary groups embed showing only important affiliations."""
    embed = discord.Embed(
        title="• Roblox Group Affiliations •", color=discord.Color.blue(), timestamp=datetime.now(timezone.utc)
    )

    important_shown = False

    # Main group
    if group_info["main_group"]:
        name, role, link = group_info["main_group"]
        embed.add_field(name="⫷ Main Group ⫸", value=f"[{name}]({link})\n**Role:** {role}", inline=False)
        important_shown = True

    # Main divisions
    if group_info["main_divisions"]:
        divisions_text = "\n\n".join(
            [f"[{name}]({link})\n**Role:** {role}" for name, role, link in group_info["main_divisions"]]
        )
        embed.add_field(name="⫷ Main Divisions ⫸", value=divisions_text, inline=False)
        important_shown = True

    # Sub divisions
    if group_info["sub_divisions"]:
        sub_divs_text = "\n\n".join(
            [f"[{name}]({link})\n**Role:** {role}" for name, role, link in group_info["sub_divisions"]]
        )
        embed.add_field(name="⫷ Sub Divisions ⫸", value=sub_divs_text, inline=False)
        important_shown = True

    if not important_shown:
        embed.description = "No significant group affiliations detected"

    return embed


def create_discord_embed(user_info: dict) -> discord.Embed:
    """Create Discord information embed."""
    embed = discord.Embed(
        title="• Discord Account Information •",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(name="User", value=f"<@{user_info['id']}>", inline=True)
    embed.add_field(name="Username", value=f"{user_info['username']}", inline=True)
    embed.add_field(name="User ID", value=f"`{user_info['id']}`", inline=True)

    embed.add_field(name="Bot Account", value="Yes" if user_info["bot"] else "No", inline=True)
    embed.add_field(name="Account Age", value=f"{user_info['account_age_days']} days", inline=True)
    embed.add_field(name="Created At", value=f"<t:{int(user_info['created_at'].timestamp())}:F>", inline=True)

    return embed


# ============================================================
# COG CLASS
# ============================================================


class BackgroundCheck(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"{self.__class__.__name__} cog has been loaded")

    async def send_check_result(self, user_data: dict, reason: str, channel: discord.TextChannel):
        """Send a deny message to the channel."""
        embed = discord.Embed(
            title="❌ User Denied",
            description=f"**{user_data.get('username', 'Unknown')}** has been denied",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Reason", value=reason, inline=False)

        await channel.send(embed=embed)

    @app_commands.command(name="bgc", description="Check a user's Roblox & Discord account information.")
    @app_commands.describe(roblox_id="The Roblox user ID to check.", discord_id="The Discord user ID to check.")
    @requires_developer()
    async def check(self, interaction: discord.Interaction, roblox_id: str, discord_id: str):
        await interaction.response.defer(ephemeral=True)
        await interaction.edit_original_response(content="⏳ Processing the check...")

        # Validate Discord ID
        try:
            discord_id_int = int(discord_id)
        except ValueError:
            await report_error(
                interaction,
                "Invalid Discord ID provided.",
                level="error",
                user_message="❌ Invalid Discord ID provided.",
            )
            return

        # Validate Roblox ID
        try:
            roblox_id_int = int(roblox_id)
        except ValueError:
            await report_error(
                interaction, "Invalid Roblox ID provided.", level="error", user_message="❌ Invalid Roblox ID provided."
            )
            return

        # Fetch Discord user info
        user_info = await fetch_discord_user_info(self.bot, discord_id_int, interaction)
        if not user_info:
            return

        # Check Discord account age
        if user_info["account_age_days"] < MIN_DISCORD_AGE_DAYS:
            await self.send_check_result(
                {"username": user_info["username"]}, reason="DISCORD ACCOUNT TOO YOUNG", channel=interaction.channel
            )
            await interaction.edit_original_response(content="✅ Check completed and logged.")
            return

        # Fetch Roblox user data using the service
        try:
            user_data = await self.bot.roblox.fetch_user_data(roblox_id_int)
        except Exception as e:
            await report_error(interaction, str(e), level="error", user_message=f"❌ {str(e)}")
            return

        # Check badge count
        if user_data["badge_count"] < MIN_BADGE_COUNT:
            await self.send_check_result(
                user_data,
                reason=f"NOT ENOUGH BADGES DETECTED ({user_data['badge_count']}/{MIN_BADGE_COUNT})",
                channel=interaction.channel,
            )
            await interaction.edit_original_response(content="✅ Check completed and logged.")
            return

        # Fetch groups using the service
        try:
            groups = await self.bot.roblox.fetch_user_groups(user_data["user_id"])
            group_info = categorize_groups(groups)
            total_groups = len(groups)
        except Exception as e:
            await report_error(interaction, f"Error fetching groups: {e}", level="error")
            group_info = {"main_divisions": [], "sub_divisions": [], "main_group": None, "all_groups": []}
            total_groups = 0

        # Generate badge graph
        badge_graph = await generate_badge_growth_graph(
            user_data["badges"],
            user_data["account_created_date"],
            user_data["username"],
            user_data["user_id"],
            interaction,
        )

        # Create embeds
        discord_embed = create_discord_embed(user_info)
        roblox_embed = create_roblox_embed(user_data, total_groups)
        groups_embed = create_groups_embed(group_info, user_data["user_id"], len(group_info["all_groups"]))

        # Send to the channel where command was used
        channel = interaction.channel
        if channel:
            # Send mention and main embeds (Roblox + Discord)
            await channel.send(embeds=[discord_embed, roblox_embed, groups_embed])

            # Send badge graph if available
            if badge_graph:
                file = discord.File(badge_graph, filename="badge_growth.png")
                await channel.send(file=file)

        await interaction.edit_original_response(content="✅ Check completed and logged.")


async def setup(bot: commands.Bot):
    """Load the BackgroundCheck cog."""
    await bot.add_cog(BackgroundCheck(bot))
