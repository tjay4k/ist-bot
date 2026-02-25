import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import asyncio
import logging
from config.config import config
from core.checks import requires_developer
from utils.embeds import create_embed

logger = logging.getLogger(__name__)


class StaffRating(commands.Cog):
    """
    Staff Rating System

    Automatically posts staff rating polls to configured channels.
    Reads staff positions from Google Sheets and creates reaction-based polls.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sheets_service = None

        # Position structure with sheet names and cells
        # Format: ("header", "Header Text") for section headers
        # Format: (sheet_name, cell_address, position_title) for staff positions
        self.POSITIONS = [
            # High Command
            ("header", "### ▬▬▬▬▬ High Command ▬▬▬▬▬"),
            ("High Command", "F14", "**Commander**"),
            ("High Command", "F15", "**ViceCommander**"),
            ("High Command", "F16", "**Executive Officer**"),

            # Riot Company Command
            ("header", "### ▬▬▬▬▬ Riot Company Command ▬▬▬▬▬"),
            ("Riot Company", "F16", "**Major**"),
            ("Riot Company", "F17", "**Captain**"),
            ("Riot Company", "F18", "**Lieutenant**"),
            ("Riot Company", "F19", "**Lieutenant**"),

            # Shock Company Command
            ("header", "### ▬▬▬▬▬ Shock Company Command ▬▬▬▬▬"),
            ("Shock Company", "F16", "**Major**"),
            ("Shock Company", "F17", "**Captain**"),
            ("Shock Company", "F18", "**Captain**"),
            ("Shock Company", "F19", "**Lieutenant**"),
            ("Shock Company", "F20", "**Lieutenant**"),
            ("Shock Company", "F21", "**Lieutenant**"),

            # Instructor Team
            ("header", "### ▬▬▬▬▬ Instructor Team Command ▬▬▬▬▬"),
            ("Instructor Team", "F16", "**Director**"),
            ("Instructor Team", "F17", "**Head Instructor**"),
        ]

        logger.info("StaffRating cog initialized")

    @commands.Cog.listener()
    async def on_ready(self):
        """Start the automatic posting task when bot is ready"""
        # Get the sheets service
        self.sheets_service = self.bot.get_service("sheets")

        if not self.sheets_service or not self.sheets_service.client:
            logger.error(
                "Sheets service not available. Staff rating will not work.")
            return

        # Start the automatic posting task
        if not self.auto_post_rating.is_running():
            self.auto_post_rating.start()
            logger.info("Automatic staff rating task started")

    # -------------------------
    # Helper Methods
    # -------------------------

    def get_guild_config(self, guild_id: int) -> dict:
        """Get staff rating config for a specific guild"""
        return config.get("staff_rating", str(guild_id), default={})

    def find_member_by_username(self, guild: discord.Guild, username: str) -> discord.Member | None:
        """
        Search for a Discord member whose display name contains the username.
        Display names follow format: [RANK] | username | timezone
        """
        if username == "N/A" or not username:
            return None

        # Search through all members
        for member in guild.members:
            # Check if username is in their display name (case-insensitive)
            if username.lower() in member.display_name.lower():
                return member

        return None

    async def post_rating_to_channel(
        self,
        channel: discord.TextChannel,
        guild: discord.Guild,
        sheet_url: str,
        mention_role_id: int | None = None
    ):
        """
        Post the staff rating to a specific channel.

        Args:
            channel: Discord channel to post to
            guild: Discord guild
            sheet_url: Google Sheets URL
            mention_role_id: Optional role ID to mention
        """
        try:
            if not self.sheets_service or not self.sheets_service.client:
                logger.error("Sheets service not initialized")
                return

            # Get reactions from config (default to traffic light emojis)
            reactions = ["🟩", "🟨", "🟥"]

            # Open spreadsheet
            spreadsheet = self.sheets_service.open_by_url(sheet_url)

            # Build intro message
            intro_text = "## Coruscant Guard Staff Rating\n"
            intro_text += "This rating is conducted to gather insight into how our officer team is perceived by the community. "
            intro_text += "Please be honest with your feedback, your responses will **not affect any promotions or demotions.** "
            intro_text += "This is solely for internal review and continuous improvement. "
            intro_text += "Your input helps us grow and improve our training environment, so we truly appreciate you taking the time to participate!"

            # Add role mention if configured
            if mention_role_id:
                intro_text = f"<@&{mention_role_id}>\n{intro_text}"

            await channel.send(intro_text)
            await asyncio.sleep(0.1)

            # Process each position
            for item in self.POSITIONS:
                if item[0] == "header":
                    # Send section header
                    await channel.send(item[1])
                    await asyncio.sleep(0.1)
                else:
                    sheet_name, cell_address, position_title = item

                    # Get the current holder from spreadsheet
                    holder = self.sheets_service.get_cell_value(
                        spreadsheet, sheet_name, cell_address
                    )

                    # Try to find the Discord member
                    member = self.find_member_by_username(guild, holder)

                    # Format the message
                    if member:
                        message_text = f"{position_title}: {member.mention}"
                    else:
                        message_text = f"{position_title}: {holder}"

                    # Send message
                    msg = await channel.send(message_text)

                    # Add reactions
                    for emoji in reactions:
                        await msg.add_reaction(emoji)
                        await asyncio.sleep(0.3)

                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(
                f"Error posting rating to channel {channel.id}: {e}", exc_info=True)
            raise

    # -------------------------
    # Commands
    # -------------------------

    @app_commands.command(
        name="post_rating",
        description="Manually post the staff rating poll"
    )
    @requires_developer()
    async def post_staff_rating(self, interaction: discord.Interaction):
        """Manually trigger staff rating post"""
        await interaction.response.defer(ephemeral=True)

        try:
            # Get guild config
            guild_config = self.get_guild_config(interaction.guild_id)

            if not guild_config:
                embed = create_embed(
                    description="❌ Staff rating is not configured for this server."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Get channel
            channel_id = guild_config.get("channel_id")
            if not channel_id:
                embed = create_embed(
                    description="❌ No rating channel configured for this server."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            channel = self.bot.get_channel(channel_id)
            if not channel:
                embed = create_embed(
                    description=f"❌ Could not find channel with ID {channel_id}"
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Get spreadsheet URL
            sheet_url = guild_config.get("spreadsheet_url")
            if not sheet_url:
                embed = create_embed(
                    description="❌ No spreadsheet URL configured for this server."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Get optional mention role
            mention_role_id = guild_config.get("mention_role_id")

            # Post the rating
            await self.post_rating_to_channel(
                channel,
                interaction.guild,
                sheet_url,
                mention_role_id
            )

            embed = create_embed(
                description="✅ Staff rating posted successfully!"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(
                f"Error in post_staff_rating command: {e}", exc_info=True)
            embed = create_embed(
                description=f"❌ Error: {str(e)}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="preview_rating",
        description="Preview staff rating data without posting"
    )
    @requires_developer()
    async def preview_rating(self, interaction: discord.Interaction):
        """Preview the current staff data with member mentions"""
        await interaction.response.defer(ephemeral=True)

        try:
            # Get guild config
            guild_config = self.get_guild_config(interaction.guild_id)

            if not guild_config:
                embed = create_embed(
                    description="❌ Staff rating is not configured for this server."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Get spreadsheet URL
            sheet_url = guild_config.get("spreadsheet_url")
            if not sheet_url:
                embed = create_embed(
                    description="❌ No spreadsheet URL configured for this server."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            if not self.sheets_service or not self.sheets_service.client:
                embed = create_embed(
                    description="❌ Sheets service not initialized. Check credentials.json"
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Open spreadsheet
            spreadsheet = self.sheets_service.open_by_url(sheet_url)

            preview_text = "**Staff Rating Preview:**\n\n"

            for item in self.POSITIONS:
                if item[0] == "header":
                    preview_text += f"\n{item[1]}\n"
                else:
                    sheet_name, cell_address, position_title = item
                    holder = self.sheets_service.get_cell_value(
                        spreadsheet, sheet_name, cell_address
                    )

                    # Try to find member
                    member = self.find_member_by_username(
                        interaction.guild, holder)

                    if member:
                        preview_text += f"{position_title}: {member.mention} ✓\n"
                    else:
                        preview_text += f"{position_title}: {holder}\n"

            # Split into multiple messages if too long
            if len(preview_text) > 2000:
                chunks = [preview_text[i:i+1900]
                          for i in range(0, len(preview_text), 1900)]
                for chunk in chunks:
                    await interaction.followup.send(chunk, ephemeral=True)
            else:
                await interaction.followup.send(preview_text, ephemeral=True)

        except Exception as e:
            logger.error(
                f"Error in preview_rating command: {e}", exc_info=True)
            embed = create_embed(
                description=f"❌ Error: {str(e)}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    # -------------------------
    # Automatic Posting
    # -------------------------

    @tasks.loop(time=time(hour=21, minute=0))  # Runs daily at 21:00 UTC
    async def auto_post_rating(self):
        """Automatically post staff rating every Sunday at 21:00 UTC"""
        # Only run on Sundays (weekday 6)
        if datetime.now().weekday() != 6:
            return

        logger.info("Auto-posting staff rating...")

        try:
            # Get all configured guilds
            config.reload()
            staff_rating_config = config.get("staff_rating", default={})

            for guild_id_str, guild_config in staff_rating_config.items():
                try:
                    guild_id = int(guild_id_str)

                    # Skip if auto_post is disabled
                    if not guild_config.get("auto_post", False):
                        continue

                    # Get required config
                    channel_id = guild_config.get("channel_id")
                    sheet_url = guild_config.get("spreadsheet_url")

                    if not channel_id or not sheet_url:
                        logger.warning(
                            f"Incomplete config for guild {guild_id}, skipping"
                        )
                        continue

                    # Get Discord objects
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        logger.warning(f"Could not find guild {guild_id}")
                        continue

                    channel = guild.get_channel(channel_id)
                    if not channel:
                        logger.warning(
                            f"Could not find channel {channel_id} in guild {guild_id}"
                        )
                        continue

                    # Get optional mention role
                    mention_role_id = guild_config.get("mention_role_id")

                    # Post the rating
                    await self.post_rating_to_channel(
                        channel,
                        guild,
                        sheet_url,
                        mention_role_id
                    )

                    logger.info(
                        f"Successfully auto-posted staff rating to guild {guild_id}")

                    # Add delay between servers to avoid rate limits
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(
                        f"Error auto-posting to guild {guild_id_str}: {e}",
                        exc_info=True
                    )
                    continue

        except Exception as e:
            logger.error(f"Error in auto_post_rating task: {e}", exc_info=True)

    @auto_post_rating.before_loop
    async def before_auto_post(self):
        """Wait until bot is ready before starting the loop"""
        await self.bot.wait_until_ready()
        logger.info("Auto-post task ready - will run Sundays at 21:00 UTC")

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.auto_post_rating.cancel()
        logger.info("StaffRating cog unloaded, auto-post task cancelled")


async def setup(bot: commands.Bot):
    await bot.add_cog(StaffRating(bot))
