import discord
from discord.ext import commands, tasks
import logging
from config.config import config
from core.checks import is_cog_enabled
from utils.embeds import create_embed
from datetime import datetime, timezone, timedelta
from typing import Sequence
import aiofiles
from pathlib import Path
from PIL import Image
import io
import asyncio

logger = logging.getLogger(__name__)

# Image cache directory
IMAGE_CACHE_DIR = Path("./cache/images")
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Caching configuration
CACHED_TYPES = {
    'image/png',
    'image/jpeg',
    'image/jpg',
    'image/webp',
    'image/gif',
}
MAX_CACHE_SIZE = 5 * 1024 * 1024  # 5MB

# ============================================================
# COG CLASS
# ============================================================


class ActionLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("ActionLog cog initialized")

    # ============================================================
    # HELPERS
    # ============================================================

    # ----------------------------
    # GENERAL HELPERS
    # ----------------------------

    async def get_log_setup(self, guild: discord.Guild, event_category: str, event_type: str) -> tuple[dict, discord.TextChannel] | tuple[None, None]:
        """Fetch event config and log channel, returns (None, None) if missing, disabled or channel not found."""
        event_config = await config.get_action_log_event(guild.id, event_category, event_type)
        logger.debug(
            f"Event config for {event_type} in guild {guild.id}: {event_config}")

        if not event_config or not event_config["channel_id"]:
            logger.debug(f"{event_type} logging disabled for guild {guild.id}")
            return None, None

        channel_id = event_config["channel_id"]
        channel = guild.get_channel(channel_id)
        if not channel:
            logger.warning(
                f"Log channel {channel_id} not found in guild {guild.id}")
            return None, None

        return event_config, channel

    async def send_log(self, channel: discord.TextChannel, embed: discord.Embed):
        """Send a log embed with error handling."""
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(
                f"Missing permissions to send to log channel {channel.id} in guild {channel.guild.id}")
        except discord.HTTPException as e:
            logger.error(f"Failed to send log embed: {e}", exc_info=True)

    @staticmethod
    def format_account_age(created_at) -> str:
        """Format account age into human readable string."""
        now = datetime.now(timezone.utc)
        delta = now - created_at

        years = delta.days // 365
        months = (delta.days % 365) // 30
        days = (delta.days % 365) % 30

        parts = []
        if years:
            parts.append(f"{years} year{'s' if years != 1 else ''}")
        if months:
            parts.append(f"{months} month{'s' if months != 1 else ''}")
        if days:
            parts.append(f"{days} day{'s' if days != 1 else ''}")

        return ", ".join(parts) or "Today"

    # ----------------------------
    # AUDIT LOG HELPERS
    # ----------------------------

    async def get_moderator_from_audit_log(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int,
        seconds: int = 3
    ) -> discord.Member | None:
        """
        Get the moderator who performed an action from audit logs.

        Args:
            guild: The guild to check
            action: The audit log action type
            target_id: The ID of the target (user/role)
            seconds: How many seconds back to check (default 3)

        Returns:
            The moderator who performed the action, or None if not found
        """
        try:
            async for entry in guild.audit_logs(
                limit=10,
                action=action,
                after=datetime.now(timezone.utc) - timedelta(seconds=seconds)
            ):
                if entry.target.id == target_id:
                    return entry.user
            return None
        except discord.Forbidden:
            logger.warning(f"No audit log access in guild {guild.id}")
            return None
        except Exception as e:
            logger.error(f"Error checking audit logs: {e}", exc_info=True)
            return None

    # ----------------------------
    # IMAGE CACHING
    # ----------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Cache images from messages for deletion logging."""
        # Skip DMs
        if not message.guild:
            return

        # Skip bot messages
        if message.author.bot:
            return

        # Check if message has attachments
        if not message.attachments:
            return

        for attachment in message.attachments:
            # Only cache allowed types
            if not attachment.content_type or attachment.content_type not in CACHED_TYPES:
                continue

            # Skip if too large
            if attachment.size > MAX_CACHE_SIZE:
                logger.debug(
                    f"Skipping {attachment.filename}: too large ({attachment.size/1024/1024:.1f}MB)")
                continue

            try:
                # Download image
                image_bytes = await attachment.read()

                # Compress image
                compressed_bytes = await self.compress_image(image_bytes, attachment.filename)

                # Create filepath
                filepath = IMAGE_CACHE_DIR / \
                    f"{message.id}_{attachment.id}_{attachment.filename}"

                # Save to disk
                async with aiofiles.open(filepath, 'wb') as f:
                    await f.write(compressed_bytes)

                # Store metadata in database
                await self.bot.db.execute(
                    """
                    INSERT INTO message_images (message_id, attachment_id, filename, filepath)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (message_id, attachment_id) DO NOTHING
                    """,
                    message.id, attachment.id, attachment.filename, str(
                        filepath)
                )

                logger.debug(
                    f"Cached image {attachment.filename} from message {message.id}")

            except discord.HTTPException as e:
                logger.error(
                    f"Failed to download attachment {attachment.id}: {e}")
            except Exception as e:
                logger.error(
                    f"Failed to cache image {attachment.id}: {e}", exc_info=True)

    @tasks.loop(hours=24)
    async def cleanup_old_images(self):
        """Delete cached images older than 30 days."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)

            # Get old images
            rows = await self.bot.db.fetch(
                "SELECT filepath FROM message_images WHERE created_at < $1",
                cutoff
            )

            deleted_count = 0
            for row in rows:
                filepath = Path(row['filepath'])
                if filepath.exists():
                    try:
                        filepath.unlink()
                        deleted_count += 1
                    except Exception as e:
                        logger.error(
                            f"Failed to delete cached image {filepath}: {e}")

            # Delete from database
            await self.bot.db.execute(
                "DELETE FROM message_images WHERE created_at < $1",
                cutoff
            )

            logger.info(
                f"Cleaned up {deleted_count} cached images older than 30 days")

        except Exception as e:
            logger.error(f"Error during image cleanup: {e}", exc_info=True)

    @cleanup_old_images.before_loop
    async def before_cleanup_old_images(self):
        """Wait for bot to be ready before starting cleanup task."""
        await self.bot.wait_until_ready()

    async def compress_image(self, image_bytes: bytes, filename: str) -> bytes:
        """Compress image to reduce file size while maintaining quality."""
        try:
            # Load image
            image = Image.open(io.BytesIO(image_bytes))

            # Convert RGBA to RGB if saving as JPEG
            if image.mode in ('RGBA', 'LA', 'P'):
                if filename.lower().endswith(('.jpg', '.jpeg')):
                    # Create white background for transparent images
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    if image.mode == 'P':
                        image = image.convert('RGBA')
                    background.paste(image, mask=image.split()
                                     [-1] if image.mode == 'RGBA' else None)
                    image = background

            # Resize if too large (Discord displays max ~1920px anyway)
            if image.width > 1920 or image.height > 1920:
                image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
                logger.debug(f"Resized image {filename} to fit 1920px")

            # Compress
            output = io.BytesIO()
            if filename.lower().endswith('.png'):
                # PNG: lossless optimization
                image.save(output, format='PNG', optimize=True)
            elif filename.lower().endswith('.gif'):
                # GIF: keep as-is (compression can break animations)
                image.save(output, format='GIF', optimize=True)
            else:
                # JPEG/WEBP: high quality compression
                save_format = 'JPEG' if filename.lower().endswith(('.jpg', '.jpeg')) else 'WEBP'
                image.save(output, format=save_format,
                           quality=92, optimize=True)

            compressed = output.getvalue()

            # Log compression ratio
            original_size = len(image_bytes)
            compressed_size = len(compressed)
            ratio = (1 - compressed_size / original_size) * 100
            logger.debug(
                f"Compressed {filename}: {original_size/1024:.1f}KB → {compressed_size/1024:.1f}KB ({ratio:.1f}% reduction)")

            return compressed

        except Exception as e:
            logger.error(
                f"Failed to compress image {filename}: {e}", exc_info=True)
            # Return original if compression fails
            return image_bytes

    @staticmethod
    def get_not_cached_reason(attachment: discord.Attachment) -> str:
        """Determine why an attachment wasn't cached."""
        if not attachment.content_type:
            return "unkown file type"

        elif attachment.size > MAX_CACHE_SIZE:
            size_mb = attachment.size / (1024 * 1024)
            return f"too large ({size_mb:1f}) MB"

        elif attachment.content_type.startswith('video/'):
            return "video files not cached"

        if attachment.content_type.startswith('audio/'):
            return "audio files not cached"

        if attachment.content_type not in CACHED_TYPES:
            return f"file type not cached"

        return "not cached"

    # ----------------------------
    # MEMBER CACHING
    # ----------------------------

    async def cache_member_info(self, member: discord.Member):
        """Cache member information and roles."""
        try:
            # Cache basic member info
            await self.bot.db.execute(
                """
                INSERT INTO guild_members (
                    guild_id, user_id, username, nickname, 
                    joined_at, account_created_at, is_bot
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (guild_id, user_id) 
                DO UPDATE SET 
                    username = EXCLUDED.username,
                    nickname = EXCLUDED.nickname,
                    cached_at = NOW()
                """,
                member.guild.id,
                member.id,
                member.name,
                member.nick,
                member.joined_at,
                member.created_at,
                member.bot
            )

            # Clear existing roles
            await self.bot.db.execute(
                "DELETE FROM member_roles WHERE guild_id = $1 AND user_id = $2",
                member.guild.id, member.id
            )

            # Cache current roles
            for role in member.roles:
                if role.is_default():  # Skip @everyone
                    continue
                await self.bot.db.execute(
                    """
                    INSERT INTO member_roles (guild_id, user_id, role_id, role_name)
                    VALUES ($1, $2, $3, $4)
                    """,
                    member.guild.id, member.id, role.id, role.name
                )

            logger.debug(
                f"Cached member info for {member.name} ({member.id}) in guild {member.guild.id}")

        except Exception as e:
            logger.error(
                f"Failed to cache member info for {member.id}: {e}", exc_info=True)

    async def get_cached_member(self, guild_id: int, user_id: int) -> dict | None:
        """Retrieve cached member information."""
        return await self.bot.db.fetchrow(
            "SELECT * FROM guild_members WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id
        )

    async def get_cached_roles(self, guild_id: int, user_id: int) -> list[dict]:
        """Retrieve cached member roles."""
        return await self.bot.db.fetch(
            "SELECT role_id, role_name FROM member_roles WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id
        )

    async def get_removal_type(self, guild: discord.Guild, member: discord.Member) -> tuple[str, discord.Member | None]:
        """
        Check audit logs to determine if removal was kick or voluntary leave.
        Returns (removal_type, moderator) where removal_type is 'kick' or 'leave'.
        """
        try:
            async for entry in guild.audit_logs(
                limit=10,
                action=discord.AuditLogAction.kick,
                after=datetime.now(timezone.utc) - timedelta(seconds=5)
            ):
                if entry.target.id == member.id:
                    return "kick", entry.user
            return "leave", None
        except discord.Forbidden:
            logger.warning(
                f"No audit log access in guild {guild.id} - assuming voluntary leave")
            return "leave", None
        except Exception as e:
            logger.error(f"Error checking audit logs: {e}", exc_info=True)
            return "leave", None

    # ============================================================
    # ACTION LOG
    # ============================================================

    # -------------------------
    # MESSAGE EVENTS
    # -------------------------

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        if not await is_cog_enabled(payload.guild_id, "action_log"):
            return

        message = payload.cached_message

        # Skip bot messages only if we have the message cached
        if message and message.author == self.bot.user:
            return

        logger.debug(
            f"on_raw_message_delete fired in guild {payload.guild_id}")

        _, channel = await self.get_log_setup(guild, "message_events", "delete")
        if not channel:
            return

        # ALWAYS check for cached images, even if message not in Discord cache
        cached_images = await self.bot.db.fetch(
            "SELECT * FROM message_images WHERE message_id = $1",
            payload.message_id
        )

        # Case 1: We have cached images but no message in Discord cache
        if cached_images and not message:
            # Log image deletion with minimal info
            if len(cached_images) == 1:
                title = "Image Deleted"
            else:
                title = f"{len(cached_images)} Images Deleted"

            embed = create_embed(
                title=title,
                description=(
                    f"**Channel:** <#{payload.channel_id}>\n"
                    f"**Author:** Unknown (message not cached)\n"
                    f"**Message ID:** {payload.message_id}\n\n"
                    f"*Message details unavailable - deleted message was not in cache*"
                ),
                color=discord.Color.orange(),
                footer=f"Message ID: {payload.message_id}",
                timestamp=True,
            )

            # Attach cached files
            files = []
            for row in cached_images:
                filepath = Path(row['filepath'])
                try:
                    if filepath.exists():
                        files.append(discord.File(
                            filepath, filename=row['filename']))
                    else:
                        logger.warning(
                            f"Cached image not found on disk: {filepath}")
                except Exception as e:
                    logger.error(f"Error loading cached image {filepath}: {e}")

            await self.send_log(channel, embed, files=files)

            # Clean up cached images from disk and database
            for row in cached_images:
                filepath = Path(row['filepath'])
                if filepath.exists():
                    try:
                        filepath.unlink()
                        logger.debug(
                            f"Deleted cached image {row['filename']} after logging")
                    except Exception as e:
                        logger.error(
                            f"Failed to delete cached image {filepath}: {e}")

            await self.bot.db.execute(
                "DELETE FROM message_images WHERE message_id = $1",
                payload.message_id
            )
            return  # Done logging, exit

        # Case 2: No message and no cached images - nothing to log
        if not message:
            return

        # Case 3: We have the message - continue with full logging
        # Determine uncached attachments
        all_attachments = message.attachments
        cached_ids = {row['attachment_id'] for row in cached_images}
        uncached_attachments = [
            att for att in all_attachments if att.id not in cached_ids]

        # Determine message type and embed properties
        has_text = bool(message.content)
        has_cached_images = bool(cached_images)

        if has_cached_images and not has_text:
            # Standalone image deletion
            if len(cached_images) == 1:
                title = "Image Deleted"
            else:
                title = f"{len(cached_images)} Images Deleted"
            color = discord.Color.orange()
            content_text = "*No text content - image only*"
        else:
            # Regular message deletion
            title = "Message Deleted"
            color = discord.Color.red()
            content_text = message.content or "*No text content*"

        # Build embed
        embed = create_embed(
            title=title,
            description=(
                f"**Author:** {message.author.mention}\n"
                f"**Channel:** {message.channel.mention}\n"
                f"**Sent:** <t:{int(message.created_at.timestamp())}:R>"
            ),
            color=color,
            footer=f"User ID: {message.author.id} • Message ID: {payload.message_id}",
            timestamp=True,
        )

        # Add message content field
        embed.add_field(name="Message:", value=content_text, inline=False)

        # Add uncached attachments info if any
        if uncached_attachments:
            uncached_info = []
            for att in uncached_attachments:
                reason = self.get_not_cached_reason(att)
                uncached_info.append(f"• `{att.filename}` ({reason})")

            uncached_text = "\n".join(uncached_info)
            embed.add_field(
                name=f"⚠️ {len(uncached_attachments)} Attachment(s) Not Cached:",
                value=uncached_text,
                inline=False
            )

        # Prepare cached image files
        files = []
        for row in cached_images:
            filepath = Path(row['filepath'])
            try:
                if filepath.exists():
                    files.append(discord.File(
                        filepath, filename=row['filename']))
                else:
                    logger.warning(
                        f"Cached image not found on disk: {filepath}")
            except Exception as e:
                logger.error(f"Error loading cached image {filepath}: {e}")

        # Send log with attachments
        await self.send_log(channel, embed, files=files)

        # Clean up cached images from disk and database
        for row in cached_images:
            filepath = Path(row['filepath'])
            if filepath.exists():
                try:
                    filepath.unlink()
                    logger.debug(
                        f"Deleted cached image {row['filename']} after logging")
                except Exception as e:
                    logger.error(
                        f"Failed to delete cached image {filepath}: {e}")

        # Delete from database
        if cached_images:
            await self.bot.db.execute(
                "DELETE FROM message_images WHERE message_id = $1",
                payload.message_id
            )

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        if not await is_cog_enabled(payload.guild_id, "action_log"):
            return

        logger.debug(
            f"on_raw_bulk_message_delete fired in guild {payload.guild_id}")

        _, channel = await self.get_log_setup(guild, "message_events", "bulk_delete")
        if not channel:
            return

        # ---------- Build message info ----------
        messages = payload.cached_messages
        message_count = len(messages) if messages else "*Unknown*"

        embed = create_embed(
            title="Bulk Messages Deleted",
            description=(
                f"**Channel:** <#{payload.channel.id}>\n"
                f"*Messages Deleted:** {message_count}"
            ),
            color=discord.Color.red(),
            timestamp=True,
        )

        await self.send_log(channel, embed)

    # ----------------------------
    # MEMBER EVENTS
    # ----------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Cache member info when they join and log the event."""
        logger.debug(
            f"on_member_join fired in guild {member.guild.id} for {member.id}")

        # Cache member info
        await self.cache_member_info(member)

        if not await is_cog_enabled(member.guild.id, "action_log"):
            return

        _, channel = await self.get_log_setup(member.guild, "member_events", "join")
        if not channel:
            return

        formatted_age = self.format_account_age(member.created_at)

        embed = create_embed(
            title="Member Joined",
            description=(
                f"**User:** {member.mention}\n"
                f"**Account Created:** <t:{int(member.created_at.timestamp())}:R>\n"
                f"**Account Age:** {formatted_age}"
            ),
            color=discord.Color.green(),
            footer=f"User ID: {member.id}",
            timestamp=True,
        )
        embed.set_thumbnail(member.display_avatar.url)

        await self.send_log(channel, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Handle member updates - roles and nickname changes."""
        # ---------- CACHING ----------

        roles_changed = before.roles != after.roles
        nickname_changed = before.nick != after.nick

        if roles_changed:
            await self.cache_member_info(after)
            logger.debug(f"Updated cached roles for {after.name} ({after.id})")

        elif nickname_changed:
            await self.bot.db.execute(
                """
                UPDATE guild_members 
                SET nickname = $1, cached_at = NOW()
                WHERE guild_id = $2 AND user_id = $3
                """,
                after.nick, after.guild.id, after.id
            )
            logger.debug(
                f"Updated cached nickname for {after.name} ({after.id})")

        # ---------- LOGGING ----------

        if not await is_cog_enabled(after.guild.id, "action_log"):
            return

        # -- ROLE CHANGE --
        if roles_changed:
            before_role_ids = {role.id for role in before.roles}
            after_role_ids = {role.id for role in after.roles}

            added_role_ids = after_role_ids - before_role_ids
            removed_role_ids = before_role_ids - after_role_ids

            # Log role additions
            if added_role_ids:
                _, channel = await self.get_log_setup(after.guild, "member_events", "role_add")
                if channel:
                    for role_id in added_role_ids:
                        role = after.guild.get_role(role_id)
                        if role and not role.is_default():  # Skip @everyone
                            # Get who added the role
                            moderator = await self.get_moderator_from_audit_log(
                                after.guild,
                                discord.AuditLogAction.member_role_update,
                                after.id
                            )

                            description = (
                                f"> **User:** {after.mention}\n"
                                f"> **Role:** {role.mention}\n"
                            )

                            if moderator:
                                description += f"> **Added by:**"

                            embed = create_embed(
                                title="Role Added",
                                description=description,
                                color=discord.Color.green(),
                                footer=f"**User ID: {after.id} | Role ID: {role.id}",
                                timestamp=True,
                            )
                            await self.send_log(channel, embed)

            # Log role removals
            if removed_role_ids:
                _, channel = await self.get_log_setup(after.guild, "member_events", "role_remove")
                if channel:
                    for role_id in removed_role_ids:
                        role = before.guild.get_role(role_id)
                        if role and not role.is_default():  # Skip @everyone
                            # Get who removed the role
                            moderator = await self.get_moderator_from_audit_log(
                                after.guild,
                                discord.AuditLogAction.member_role_update,
                                after.id
                            )

                            description = (
                                f"**User:** {after.mention}\n"
                                f"**Role:** {role.mention}\n"
                            )

                            if moderator:
                                description += f"**Removed by:** {moderator.mention}"

                            embed = create_embed(
                                title="Role Removed",
                                description=description,
                                color=discord.Color.red(),
                                footer=f"User ID: {after.id} | Role ID: {role.id}",
                                timestamp=True,
                            )
                            await self.send_log(channel, embed)

        # -- NICKNAME CHANGE --
        if before.nick != after.nick:
            _, channel = await self.get_log_setup(after.guild, "member_events", "nickname_change")
            if channel:
                old_nick = before.nick or "*No nickname*"
                new_nick = after.nick or "*No nickname*"

                # Get who changed the nickname (could be self or moderator)
                moderator = await self.get_moderator_from_audit_log(
                    after.guild,
                    discord.AuditLogAction.member_update,
                    after.id
                )

                description = (
                    f"**User:** {after.mention}\n"
                    f"**Old Nickname:** {old_nick}\n"
                    f"**New Nickname:** {new_nick}\n"
                )

                if moderator and moderator.id != after.id:
                    # Moderator changed it
                    description += f"**Changed by:** {moderator.mention}"
                elif moderator and moderator.id == after.id:
                    # User changed it themselves
                    description += f"**Changed by:** Self"
                else:
                    # Couldn't determine
                    description += f"**Changed by:** Unknown"

                embed = create_embed(
                    title="Nickname Changed",
                    description=description,
                    color=discord.Color.blue(),
                    footer=f"User ID: {after.id}",
                    timestamp=True,
                )
                await self.send_log(channel, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Handle member removal - could be leave or kick."""
        logger.debug(
            f"on_member_remove fired in guild {member.guild.id} for {member.id}")

        if not await is_cog_enabled(member.guild.id, "action_log"):
            return

        # Wait briefly to see if ban event fires
        await asyncio.sleep(1)

        # Check if this was a ban (on_member_ban would have fired)
        if hasattr(self, 'recent_bans') and (member.guild.id, member.id) in self.recent_bans:
            # Skip - ban event will handle logging
            del self.recent_bans[(member.guild.id, member.id)]
            return

        # Check if this was a kick
        removal_type, moderator = await self.get_removal_type(member.guild, member)

        # Get cached member info
        cached = await self.get_cached_member(member.guild.id, member.id)
        if not cached:
            logger.warning(
                f"No cached info for member {member.id} in guild {member.guild.id}")
            return

        # Get cached roles
        roles = await self.get_cached_roles(member.guild.id, member.id)
        roles_text = ", ".join(f"`{r['role_name']}`" for r in roles) or "None"

        # Calculate time in server
        time_in_server = datetime.now(timezone.utc) - cached['joined_at']
        days = time_in_server.days

        # Determine log channel and title based on removal type
        if removal_type == "kick":
            _, channel = await self.get_log_setup(member.guild, "moderation_events", "kick")
            title = "Member Kicked"
            color = discord.Color.orange()
            description = (
                f"**User:** {member.mention}\n"
                f"**Kicked by:** {moderator.mention if moderator else 'Unknown'}\n"
                f"**Joined:** <t:{int(cached['joined_at'].timestamp())}:R>\n"
                f"**Time in Server:** {days} days\n"
                f"**Roles:** {roles_text}"
            )
        else:
            _, channel = await self.get_log_setup(member.guild, "member_events", "leave")
            title = "Member Left"
            color = discord.Color.red()
            description = (
                f"**User:** {member.mention}\n"
                f"**Joined:** <t:{int(cached['joined_at'].timestamp())}:R>\n"
                f"**Time in Server:** {days} days\n"
                f"**Roles:** {roles_text}"
            )

        if not channel:
            return

        embed = create_embed(
            title=title,
            description=description,
            color=color,
            footer=f"User ID: {member.id}",
            timestamp=True,
        )

        await self.send_log(channel, embed)

    # ('member_events', 'leave'),
    # ('member_events', 'nickname_change'),
    # ('member_events', 'role_add'),
    # ('member_events', 'role_remove'),
    # ('member_events', 'invite'),

    # ----------------------------
    # Moderation events
    # ----------------------------

    # -- moderation_events
    # ('moderation_events', 'unban'),
    # ('moderation_events', 'kick'),
    # ('moderation_events', 'timeout'),
    # ('moderation_events', 'moderator_commands'),

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Handle member ban."""
        logger.debug(f"on_member_ban fired in guild {guild.id} for {user.id}")

        # Track recent ban to avoid double logging in on_member_remove
        if not hasattr(self, 'recent_bans'):
            self.recent_bans = {}

        self.recent_bans[(guild.id, user.id)] = datetime.now(timezone.utc)

        # Clean up old entries (older than 5 seconds)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.recent_bans = {
            k: v for k, v in self.recent_bans.items()
            if v > cutoff
        }

        if not await is_cog_enabled(guild.id, "action_log"):
            return

        _, channel = await self.get_log_setup(guild, "moderation_events", "ban")
        if not channel:
            return

        # Get cached member info if available
        cached = await self.get_cached_member(guild.id, user.id)

        if cached:
            roles = await self.get_cached_roles(guild.id, user.id)
            roles_text = ", ".join(
                f"`{r['role_name']}`" for r in roles) or "None"

            description = (
                f"**User:** {user.mention}\n"
                f"**Joined:** <t:{int(cached['joined_at'].timestamp())}:R>\n"
                f"**Roles:** {roles_text}"
            )
        else:
            description = f"**User:** {user.mention}"

        embed = create_embed(
            title="Member Banned",
            description=description,
            color=discord.Color.dark_red(),
            author_name=user.name,
            author_icon_url=user.display_avatar.url,
            footer=f"User ID: {user.id}",
            timestamp=True,
        )

        await self.send_log(channel, embed)

    # ----------------------------
    # Emoji events
    # ----------------------------

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before: Sequence[discord.Emoji], after: Sequence[discord.Emoji]):
        if not await is_cog_enabled(guild.id, "action_log"):
            return

        logger.debug(
            f"on_guild_emojis_update fired in {guild.id}")

        before_ids = {emoji.id for emoji in before}
        after_ids = {emoji.id for emoji in after}

        # -- Check for created emojis --
        created_ids = after_ids - before_ids
        if created_ids:
            _, channel = await self.get_log_setup(guild, "emoji_events", "create")
            if channel:
                for emoji in after:
                    if emoji.id in created_ids:
                        embed = create_embed(
                            title="Emoji Created",
                            description=(
                                f"**Emoji: {emoji}\n"
                                f"**Name:** {emoji.name}\n"
                                f"**Animated:** {'Yes' if emoji.animated else 'No'}\n"
                                f"**ID:** {emoji.id}"
                            ),
                            color=discord.Color.green(),
                            footer=f"Emoji ID: {emoji.id}",
                            timestamp=True,
                        )
                        await self.send_log(channel, embed)

        # -- Check for deleted emojis --
        deleted_ids = before_ids - after_ids
        if deleted_ids:
            _, channel = await self.get_log_setup(guild, "emoji_events", "delete")
            if channel:
                for emoji in before:
                    if emoji.id in deleted_ids:
                        embed = create_embed(
                            title="Emoji Deleted",
                            description=(
                                f"**Name:** {emoji.name}\n"
                                f"**Animated:** {'Yes' if emoji.animated else 'No'}\n"
                                f"**ID:** {emoji.id}"
                            ),
                            color=discord.Color.red(),
                            footer=f"Emoji ID: {emoji.id}",
                            timestamp=True,
                        )
                        await self.send_log(channel, embed)

        # -- Check for edited emojis --
        for old_emoji in before:
            if old_emoji.id in after_ids:
                new_emoji = discord.utils.get(after, id=old_emoji.id)
                if new_emoji and old_emoji.name != new_emoji.name:
                    _, channel = await self.get_log_setup(guild, "emoji_events", "name_change")
                    if channel:
                        embed = create_embed(
                            title="Emoji Edited",
                            description=(
                                f"**Emoji: {new_emoji}\n"
                                f"**Old name:** {old_emoji.name}\n"
                                f"**New name:** {new_emoji.name}\n"
                                f"**ID:** {emoji.id}"
                            ),
                            color=discord.Color.yellow(),
                            footer=f"Emoji ID: {new_emoji.id}",
                            timestamp=True,
                        )
                        await self.send_log(channel, embed)

    # ----------------------------
    # Voice Channel Events
    # ----------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not await is_cog_enabled(member.guild.id, "action_log"):
            return

        logger.debug(
            f"on_voice_state_update fired in {member.guild.id}")

        # -- Join --
        if before.channel is None and after.channel is not None:
            _, channel = await self.get_log_setup(member.guild, "voice_events", "join")
            if channel:
                embed = create_embed(
                    title="Voice Channel Join",
                    description=(
                        f"**User:** {member.mention}\n"
                        f"**Channel:** {after.channel.mention}"
                    ),
                    color=discord.Color.green(),
                    footer=f"User ID: {member.id} | Channel ID: {after.channel.id}",
                    timestamp=True,
                )
                await self.send_log(channel, embed)

        # -- Leave --
        elif before.channel is not None and after.channel is None:
            _, channel = await self.get_log_setup(member.guild, "voice_events", "leave")
            if channel:
                embed = create_embed(
                    title="Voice Channel Leave",
                    description=(
                        f"**User:** {member.mention}\n"
                        f"**Channel:** {before.channel.mention}"
                    ),
                    color=discord.Color.red(),
                    footer=f"User ID: {member.id} | Channel ID: {before.channel.id}",
                    timestamp=True,
                )
                await self.send_log(channel, embed)

        # -- Move --
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            _, channel = await self.get_log_setup(member.guild, "voice_events", "move")
            if channel:
                embed = create_embed(
                    title="Voice Channel Move",
                    description=(
                        f"**User:** {member.mention}\n"
                        f"**Channel:** {before.channel.mention} → {after.channel.mention}"
                    ),
                    color=discord.Color.blue(),
                    footer=f"User ID: {member.id} | Channel ID: {after.channel.id}",
                    timestamp=True,
                )
                await self.send_log(channel, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActionLog(bot))
