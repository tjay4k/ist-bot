"""
Action Logging Cog

This cog handles comprehensive server event logging including:
- Message events (delete, edit, bulk delete) with image caching
- Member events (join, leave, kick, ban, unban, timeout) with data caching and moderator tracking
- Role changes (add, remove) with moderator tracking
- Nickname changes with moderator tracking
- Emoji events (create, delete, rename)
- Voice events (join, leave, move)

Features:
- Image caching system with compression (stores images for 30 days)
- Member data caching for historical logs
- Audit log integration to track who performed actions
- Automatic cleanup tasks
"""

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

# ============================================================
# CONSTANTS
# ============================================================

# Image cache directory (auto-created if doesn't exist)
IMAGE_CACHE_DIR = Path("./cache/images")
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# File types allowed for caching
CACHED_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
}

# Maximum file size for caching (5MB)
MAX_CACHE_SIZE = 5 * 1024 * 1024


# ============================================================
# COG CLASS
# ============================================================


class ActionLog(commands.Cog):
    """Handles action logging for all server events."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.recent_bans = {}  # Track recent bans to avoid double logging
        logger.info("ActionLog cog initialized")
        self.cleanup_old_images.start()  # Start background cleanup task

    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        self.cleanup_old_images.cancel()

    # ============================================================
    # HELPER METHODS
    # ============================================================

    # ----------------------------
    # General Helpers
    # ----------------------------

    async def get_log_setup(
        self,
        guild: discord.Guild,
        event_category: str,
        event_type: str,
    ) -> tuple[dict, discord.TextChannel] | tuple[None, None]:
        """
        Fetch event config and log channel from database.

        Args:
            guild: The guild to check
            event_category: Category (e.g., 'message_events', 'member_events')
            event_type: Specific event (e.g., 'delete', 'join')

        Returns:
            Tuple of (event_config dict, channel) or (None, None) if disabled/not found.
        """
        event_config = await config.get_action_log_event(guild.id, event_category, event_type)
        logger.debug(f"Event config for {event_type} in guild {guild.id}: {event_config}")

        if not event_config or not event_config["channel_id"]:
            logger.debug(f"{event_type} logging disabled for guild {guild.id}")
            return None, None

        channel_id = event_config["channel_id"]
        channel = guild.get_channel(channel_id)
        if not channel:
            logger.warning(f"Log channel {channel_id} not found in guild {guild.id}")
            return None, None

        return event_config, channel

    async def send_log(self, channel: discord.TextChannel, embed: discord.Embed, files: list = None):
        """
        Send a log embed to the specified channel with error handling.

        Args:
            channel: Channel to send to
            embed: Embed to send
            files: Optional list of discord.File objects to attach
        """
        try:
            await channel.send(embed=embed, files=files or [])
        except discord.Forbidden:
            logger.warning(f"Missing permissions to send to log channel {channel.id} in guild {channel.guild.id}")
        except discord.HTTPException as e:
            logger.error(f"Failed to send log embed: {e}", exc_info=True)

    @staticmethod
    def format_account_age(created_at: datetime) -> str:
        """
        Format account age into human readable string.

        Args:
            created_at: When the account was created

        Returns:
            Formatted string like "2 years, 3 months, 5 days" or "Today"
        """
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

    @staticmethod
    def get_not_cached_reason(attachment: discord.Attachment) -> str:
        """
        Determine why an attachment wasn't cached.

        Args:
            attachment: The Discord attachment

        Returns:
            Human-readable reason string
        """
        if not attachment.content_type:
            return "unknown file type"
        elif attachment.size > MAX_CACHE_SIZE:
            size_mb = attachment.size / (1024 * 1024)
            return f"too large ({size_mb:.1f} MB)"
        elif attachment.content_type.startswith("video/"):
            return "video files not cached"
        elif attachment.content_type.startswith("audio/"):
            return "audio files not cached"
        elif attachment.content_type not in CACHED_TYPES:
            return "file type not cached"
        else:
            return "not cached"

    def db_available(self) -> bool:
        """Check if database is available."""
        return hasattr(self.bot, "db") and self.bot.db is not None

    # ----------------------------
    # Event Validation Helpers
    # ----------------------------

    async def validate_event(
        self,
        guild: discord.Guild,
        event_category: str,
        event_type: str,
        event_name: str = "event",
    ) -> discord.TextChannel | None:
        """
        Universal event validation helper - works for ALL event types.

        Performs standard validation checks:
        - Checks if action logging is enabled for this guild
        - Logs debug message
        - Retrieves and validates log channel configuration

        Args:
            guild: The guild object (for regular events) or guild ID (for raw events)
            event_category: Event category (e.g., 'message_events', 'member_events')
            event_type: Event type (e.g., 'delete', 'join', 'create')
            event_name: Event name for debug logging (e.g., 'on_member_join')

        Returns:
            Log channel if all checks pass, None otherwise

        Example:
            channel = await self.validate_event(
                member.guild, "member_events", "join", "on_member_join"
            )
            if not channel:
                return
        """
        # Handle both Guild objects and guild IDs
        guild_id = guild.id if isinstance(guild, discord.Guild) else guild
        guild_obj = guild if isinstance(guild, discord.Guild) else self.bot.get_guild(guild)

        # Check if guild exists (for raw events)
        if not guild_obj:
            return None

        # Check if cog enabled
        if not await is_cog_enabled(guild_id, "action_log"):
            return None

        # Debug logging
        logger.debug(f"{event_name} fired in guild {guild_id}")

        # Get and validate log channel
        _, channel = await self.get_log_setup(guild_obj, event_category, event_type)
        return channel

    async def raw_event_validation(
        self, payload_guild_id: int | None, event_category: str, event_type: str, event_name: str = "event"
    ) -> tuple[discord.Guild, discord.TextChannel] | tuple[None, None]:
        """
        Validate raw event and get log channel.

        Performs all standard checks for raw events:
        - Ensures event occurred in a guild (not DM)
        - Verifies bot has access to the guild
        - Checks if action logging is enabled
        - Retrieves configured log channel

        Args:
            payload_guild_id: Guild ID from raw event payload
            event_category: Event category (e.g., 'message_events')
            event_type: Event type (e.g., 'delete', 'edit')
            event_name: Event name for debug logging

        Returns:
            Tuple of (guild, channel) if valid, or (None, None) if any check fails
        """
        # Check if in guild (not DM)
        if not payload_guild_id:
            return None, None

        # User the universal validate_event helper
        channel = await self.validate_event(payload_guild_id, event_category, event_type, event_name)
        if not channel:
            return None, None

        # Get guild object for return
        guild = self.bot.get_guild(payload_guild_id)
        return guild, channel

    # ----------------------------
    # Audit Log Helpers
    # ----------------------------

    async def get_moderator_from_audit_log(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int,
        seconds: int = 3,
        max_attempts: int = 1,
        retry_delay: float = 0.2,
    ) -> discord.Member | None:
        """
        Get the moderator who performed an action from audit logs.

        Supports retry logic for actions where audit logs may lag (like message deletes).

        Args:
            guild: The guild to check
            action: The audit log action type
            target_id: The ID of the target (user, role, message author)
            seconds: How many seconds back to check (default 3)
            max_attempts: Number of retry attempts (default 1 for instant actions,
                        use 2 for message_delete/member_move which have audit log delay)
            retry_delay: Seconds to wait between retries (default 0.2)

        Returns:
            The moderator who performed the action, or None if not found/no access
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=seconds)
            for attempt in range(max_attempts):
                async for entry in guild.audit_logs(
                    limit=10,
                    action=action,
                    after=cutoff_time,
                ):
                    # Skip bulk deletes for message delete actions
                    if action == discord.AuditLogAction.message_delete:
                        extra = entry.extra
                        if hasattr(extra, "count") and extra.count > 1:
                            continue

                    # Check if target matches
                    if entry.target and entry.target.id == target_id:
                        return entry.user, entry.reason

                # Retry logic: wait and try again if attempts remain
                if attempt < max_attempts - 1:
                    await asyncio.sleep(retry_delay)

            return None, None

        except discord.Forbidden:
            logger.debug(f"No audit log access in guild {guild.id}")
            return None, None
        except Exception as e:
            logger.error(f"Error checking audit logs: {e}", exc_info=True)
            return None, None

    # ----------------------------
    # Image Caching
    # ----------------------------

    async def compress_image(self, image_bytes: bytes, filename: str) -> bytes:
        """
        Compress image to reduce file size while maintaining quality.

        Process:
        - Converts RGBA to RGB for JPEG compatibility
        - Resizes if larger than 1920px (Discord's display limit)
        - Applies format-specific compression (PNG: lossless, JPEG/WEBP: 92% quality)

        Args:
            image_bytes: Raw image bytes
            filename: Original filename (determines format)

        Returns:
            Compressed image bytes (or original if compression fails)
        """
        try:
            # Load image
            image = Image.open(io.BytesIO(image_bytes))

            # Convert RGBA to RGB if saving as JPEG (JPEG doesn't support transparency)
            if image.mode in ("RGBA", "LA", "P"):
                if filename.lower().endswith((".jpg", ".jpeg")):
                    # Create white background for transparent images
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    if image.mode == "P":
                        image = image.convert("RGBA")
                    background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
                    image = background

            # Resize if too large (Discord displays max ~1920px anyway)
            if image.width > 1920 or image.height > 1920:
                image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
                logger.debug(f"Resized image {filename} to fit 1920px")

            # Compress based on format
            output = io.BytesIO()
            if filename.lower().endswith(".png"):
                # PNG: lossless optimization
                image.save(output, format="PNG", optimize=True)
            elif filename.lower().endswith(".gif"):
                # GIF: optimize without breaking animations
                image.save(output, format="GIF", optimize=True)
            else:
                # JPEG/WEBP: high quality compression (92%)
                save_format = "JPEG" if filename.lower().endswith((".jpg", ".jpeg")) else "WEBP"
                image.save(output, format=save_format, quality=92, optimize=True)

            compressed = output.getvalue()

            # Log compression ratio
            original_size = len(image_bytes)
            compressed_size = len(compressed)
            ratio = (1 - compressed_size / original_size) * 100
            logger.debug(
                f"Compressed {filename}: {original_size/1024:.1f}KB → "
                f"{compressed_size/1024:.1f}KB ({ratio:.1f}% reduction)"
            )

            return compressed

        except Exception as e:
            logger.error(f"Failed to compress image {filename}: {e}", exc_info=True)
            # Return original if compression fails
            return image_bytes

    # ----------------------------
    # Member Caching
    # ----------------------------

    async def cache_member_info(self, member: discord.Member):
        """
        Cache member information and roles to database.

        Caches:
        - Basic info (username, nickname, join date, account creation date)
        - All current roles (with names)

        Args:
            member: The member to cache
        """
        if not self.db_available():
            logger.debug(f"Database not available, skipping member cache for {member.id}")
            return

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
                member.bot,
            )

            # Clear existing roles and re-insert current ones
            await self.bot.db.execute(
                "DELETE FROM member_roles WHERE guild_id = $1 AND user_id = $2", member.guild.id, member.id
            )

            # Cache current roles (skip @everyone)
            for role in member.roles:
                if role.is_default():
                    continue
                await self.bot.db.execute(
                    """
                    INSERT INTO member_roles (guild_id, user_id, role_id, role_name)
                    VALUES ($1, $2, $3, $4)
                    """,
                    member.guild.id,
                    member.id,
                    role.id,
                    role.name,
                )

            logger.debug(f"Cached member info for {member.name} ({member.id}) in guild {member.guild.id}")

        except Exception as e:
            logger.error(f"Failed to cache member info for {member.id}: {e}", exc_info=True)

    async def get_cached_member(self, guild_id: int, user_id: int) -> dict | None:
        """
        Retrieve cached member information from database.

        Args:
            guild_id: Guild ID
            user_id: User ID

        Returns:
            Dict with member data or None if not found
        """
        if not self.db_available():
            return None

        return await self.bot.db.fetchrow(
            "SELECT * FROM guild_members WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )

    async def get_cached_roles(self, guild_id: int, user_id: int) -> list[dict]:
        """
        Retrieve cached member roles from database.

        Args:
            guild_id: Guild ID
            user_id: User ID

        Returns:
            List of dicts with role_id and role_name
        """
        if not self.db_available():
            return []

        return await self.bot.db.fetch(
            "SELECT role_id, role_name FROM member_roles WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )

    # ============================================================
    # BACKGROUND TASKS
    # ============================================================

    @tasks.loop(hours=24)
    async def cleanup_old_images(self):
        """
        Delete cached images older than 30 days.

        Runs every 24 hours automatically.
        Cleans up both disk files and database entries.
        """
        try:
            # ✅ Check if database is available
            if not hasattr(self.bot, "db") or self.bot.db is None:
                logger.warning("Database not available, skipping image cleanup")
                return
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)

            # Get old images from database
            rows = await self.bot.db.fetch("SELECT filepath FROM message_images WHERE created_at < $1", cutoff)

            # Delete files from disk
            deleted_count = 0
            for row in rows:
                filepath = Path(row["filepath"])
                if filepath.exists():
                    try:
                        filepath.unlink()
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete cached image {filepath}: {e}")

            # Delete from database
            await self.bot.db.execute("DELETE FROM message_images WHERE created_at < $1", cutoff)

            logger.info(f"Cleaned up {deleted_count} cached images older than 30 days")

        except Exception as e:
            logger.error(f"Error during image cleanup: {e}", exc_info=True)

    @cleanup_old_images.before_loop
    async def before_cleanup_old_images(self):
        """Wait for bot to be ready before starting cleanup task."""
        await self.bot.wait_until_ready()

        # ✅ Wait up to 30 seconds for database
        for _ in range(30):
            if hasattr(self.bot, "db") and self.bot.db is not None:
                logger.info("Database ready, starting image cleanup task")
                return
            await asyncio.sleep(1)

        logger.warning("Database not ready after 30 seconds")

    # ============================================================
    # EVENT LISTENERS
    # ============================================================

    # ----------------------------
    # Image Caching (on_message)
    # ----------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Cache images from messages for deletion logging.

        Automatically caches:
        - Images (PNG, JPEG, WEBP) under 5MB
        - GIFs under 5MB

        Skips:
        - DM messages
        - Bot messages
        - Videos, audio, and other file types
        - Files larger than 5MB
        """
        # Skip DMs
        if not message.guild:
            return

        # Skip bot messages
        if message.author.bot:
            return

        if not self.db_available():
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
                logger.debug(f"Skipping {attachment.filename}: too large ({attachment.size/1024/1024:.1f}MB)")
                continue

            try:
                # Download image
                image_bytes = await attachment.read()

                # Compress image
                compressed_bytes = await self.compress_image(image_bytes, attachment.filename)

                # Create filepath
                filepath = IMAGE_CACHE_DIR / f"{message.id}_{attachment.id}_{attachment.filename}"

                # Save to disk
                async with aiofiles.open(filepath, "wb") as f:
                    await f.write(compressed_bytes)

                # Store metadata in database
                await self.bot.db.execute(
                    """
                    INSERT INTO message_images (message_id, attachment_id, filename, filepath)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (message_id, attachment_id) DO NOTHING
                    """,
                    message.id,
                    attachment.id,
                    attachment.filename,
                    str(filepath),
                )

                logger.debug(f"Cached image {attachment.filename} from message {message.id}")

            except discord.HTTPException as e:
                logger.error(f"Failed to download attachment {attachment.id}: {e}")
            except Exception as e:
                logger.error(f"Failed to cache image {attachment.id}: {e}", exc_info=True)

    # ----------------------------
    # Message Events
    # ----------------------------

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """
        Handle message deletion with cached image attachment and moderator tracking.

        Three cases:
        1. Cached images exist, message not in cache → Log images with minimal info
        2. No message, no images → Skip (nothing to log)
        3. Message exists → Full logging with images, details, and who deleted it

        Features:
        - Attaches cached images to deletion log
        - Shows which attachments weren't cached and why
        - Shows who deleted the message (self, moderator, or unknown)
        - Different embed style for image-only vs text messages
        """
        message = payload.cached_message

        # Skip bot messages only if we have the message cached
        if message and message.author == self.bot.user:
            return

        # Use raw_event_validation for standard checks
        guild, channel = await self.raw_event_validation(
            payload.guild_id, "message_events", "delete", "on_raw_message_delete"
        )
        if not guild:
            return

        # Check for cached images, even if message not in Discord cache
        cached_images = await self.bot.db.fetch(
            "SELECT * FROM message_images WHERE message_id = $1", payload.message_id
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
                color=discord.Color.red(),
                footer=f"Message ID: {payload.message_id}",
                timestamp=True,
            )

            # Attach cached files
            files = []
            for row in cached_images:
                filepath = Path(row["filepath"])
                try:
                    if filepath.exists():
                        files.append(discord.File(filepath, filename=row["filename"]))
                    else:
                        logger.warning(f"Cached image not found on disk: {filepath}")
                except Exception as e:
                    logger.error(f"Error loading cached image {filepath}: {e}")

            await self.send_log(channel, embed, files=files)

            # Clean up cached images from disk and database
            for row in cached_images:
                filepath = Path(row["filepath"])
                if filepath.exists():
                    try:
                        filepath.unlink()
                        logger.debug(f"Deleted cached image {row['filename']} after logging")
                    except Exception as e:
                        logger.error(f"Failed to delete cached image {filepath}: {e}")

            await self.bot.db.execute("DELETE FROM message_images WHERE message_id = $1", payload.message_id)
            return  # Done logging, exit

        # Case 2: No message and no cached images - nothing to log
        if not message:
            return

        # Case 3: We have the message - continue with full logging
        # Try to determine who deleted the message (with retries for audit log delay)
        moderator, _ = await self.get_moderator_from_audit_log(
            guild,
            discord.AuditLogAction.message_delete,
            message.author.id,
            seconds=5,
            max_attempts=2,
            retry_delay=0.2,
        )

        # Determine uncached attachments
        all_attachments = message.attachments
        cached_ids = {row["attachment_id"] for row in cached_images}
        uncached_attachments = [att for att in all_attachments if att.id not in cached_ids]

        # Determine message type and embed properties
        has_text = bool(message.content)
        has_cached_images = bool(cached_images)

        if has_cached_images and not has_text:
            # Standalone image deletion
            if len(cached_images) == 1:
                title = "Image Deleted"
            else:
                title = f"{len(cached_images)} Images Deleted"
            color = discord.Color.red()
            content_text = "*No text content - image only*"
        else:
            # Regular message deletion
            title = "Message Deleted"
            color = discord.Color.red()
            content_text = message.content or "*No text content*"

        # Build description
        description_parts = [
            f"**Author:** {message.author.mention}",
            f"**Channel:** {message.channel.mention}",
            f"**Sent:** <t:{int(message.created_at.timestamp())}:R>",
        ]

        # Add deleter info if found
        if moderator:
            if moderator.id == message.author.id:
                description_parts.append(f"**Deleted by:** Self")
            else:
                description_parts.append(f"**Deleted by:** {moderator.mention}")

        description = "\n".join(description_parts)

        # Build embed
        embed = create_embed(
            title=title,
            description=description,
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
                name=f"⚠️ {len(uncached_attachments)} Attachment(s) Not Cached:", value=uncached_text, inline=False
            )

        # Prepare cached image files
        files = []
        for row in cached_images:
            filepath = Path(row["filepath"])
            try:
                if filepath.exists():
                    files.append(discord.File(filepath, filename=row["filename"]))
                else:
                    logger.warning(f"Cached image not found on disk: {filepath}")
            except Exception as e:
                logger.error(f"Error loading cached image {filepath}: {e}")

        # Send log with attachments
        await self.send_log(channel, embed, files=files)

        # Clean up cached images from disk and database
        for row in cached_images:
            filepath = Path(row["filepath"])
            if filepath.exists():
                try:
                    filepath.unlink()
                    logger.debug(f"Deleted cached image {row['filename']} after logging")
                except Exception as e:
                    logger.error(f"Failed to delete cached image {filepath}: {e}")

        # Delete from database
        if cached_images:
            await self.bot.db.execute("DELETE FROM message_images WHERE message_id = $1", payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        """Handle bulk message deletion (e.g., purge command)."""
        # Use raw_event_validation for standard checks
        guild, channel = await self.raw_event_validation(
            payload.guild_id, "message_events", "bulk_delete", "on_raw_bulk_message_delete"
        )
        if not guild:
            return

        # Get message count
        messages = payload.cached_messages
        message_count = len(messages) if messages else len(payload.message_ids)

        embed = create_embed(
            title="Bulk Messages Deleted",
            description=(f"**Channel:** <#{payload.channel_id}>\n" f"**Messages Deleted:** {message_count}"),
            color=discord.Color.red(),
            timestamp=True,
        )

        await self.send_log(channel, embed)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        """
        Handle message edits.

        Shows before and after content. If message isn't cached, shows only after content.
        """
        guild, channel = await self.raw_event_validation(
            payload.guild_id, "message_events", "edit", "on_raw_message_edit"
        )
        if not guild:
            return

        # Check if we have the after message
        if not payload.message:
            return

        # Skip bot messages
        if payload.message.author.bot:
            return

        # Get before and after content
        if payload.cached_message:
            # We have both before and after
            before_content = payload.cached_message.content
            after_content = payload.message.content

            # Skip if content didn't change (might be embed-only edit)
            if before_content == after_content:
                return
        else:
            # Only have after content
            before_content = "*Message not in cache*"
            after_content = payload.message.content

        # Build embed
        embed = create_embed(
            title="Message Edited",
            description=(
                f"**Author:** {payload.message.author.mention}\n"
                f"**Channel:** {payload.message.channel.mention}\n"
                f"**[Jump to Message]({payload.message.jump_url})**"
            ),
            color=discord.Color.orange(),
            footer=f"User ID: {payload.message.author.id} • Message ID: {payload.message.id}",
            timestamp=True,
        )

        # Add before/after fields
        embed.add_field(
            name="Before:",
            value=before_content[:1024] if before_content else "*Empty*",
            inline=False,
        )
        embed.add_field(
            name="After:",
            value=after_content[:1024] if after_content else "*Empty*",
            inline=False,
        )

        # Send embed
        await self.send_log(channel, embed)

    # ----------------------------
    # Member Events
    # ----------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Cache member info when they join and log the event."""
        # Cache member info (always happens)
        await self.cache_member_info(member)

        channel = await self.validate_event(member.guild, "member_events", "join", "on_member_join")
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

        await self.send_log(channel, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Handle member updates - roles, nickname changes, and timeouts.

        This listener handles both caching (always) and logging (if enabled).
        """
        await asyncio.sleep(0.5)
        # ========== CACHING (Always happens) ==========

        roles_changed = before.roles != after.roles
        nickname_changed = before.nick != after.nick

        if roles_changed:
            # Roles changed - update full cache
            await self.cache_member_info(after)
            logger.debug(f"Updated cached roles for {after.name} ({after.id})")
        elif nickname_changed:
            # Only nickname changed - efficient update
            if not self.db_available():
                await self.bot.db.execute(
                    """
                    UPDATE guild_members 
                    SET nickname = $1, cached_at = NOW()
                    WHERE guild_id = $2 AND user_id = $3
                    """,
                    after.nick,
                    after.guild.id,
                    after.id,
                )
                logger.debug(f"Updated cached nickname for {after.name} ({after.id})")

        # ========== LOGGING (Only if enabled) ==========

        if not await is_cog_enabled(after.guild.id, "action_log"):
            return

        # --- ROLE CHANGES ---
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
                            moderator, _ = await self.get_moderator_from_audit_log(
                                after.guild, discord.AuditLogAction.member_role_update, after.id
                            )

                            description = f"**User:** {after.mention}\n" f"**Role:** {role.mention}\n"

                            if moderator:
                                description += f"**Added by:** {moderator.mention}"

                            embed = create_embed(
                                title="Role Added",
                                description=description,
                                color=discord.Color.green(),
                                footer=f"User ID: {after.id} | Role ID: {role.id}",
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
                            moderator, _ = await self.get_moderator_from_audit_log(
                                after.guild, discord.AuditLogAction.member_role_update, after.id
                            )

                            description = f"**User:** {after.mention}\n" f"**Role:** {role.mention}\n"

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

        # --- NICKNAME CHANGES ---
        if nickname_changed:
            _, channel = await self.get_log_setup(after.guild, "member_events", "nickname_change")
            if channel:
                old_nick = before.nick or "*No nickname*"
                new_nick = after.nick or "*No nickname*"

                # Get who changed the nickname
                moderator, _ = await self.get_moderator_from_audit_log(
                    after.guild, discord.AuditLogAction.member_update, after.id
                )

                description = (
                    f"**User:** {after.mention}\n" f"**Old Nickname:** {old_nick}\n" f"**New Nickname:** {new_nick}\n"
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

        # --- TIMEOUT CHANGES ---
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until:
                # Member was timed out
                _, channel = await self.get_log_setup(after.guild, "moderation_events", "timeout")
                if channel:
                    # Get who timed them out
                    moderator, _ = await self.get_moderator_from_audit_log(
                        after.guild, discord.AuditLogAction.member_update, after.id
                    )

                    description = (
                        f"**User:** {after.mention}\n"
                        f"**Timeout Until:** <t:{int(after.timed_out_until.timestamp())}:F>\n"
                    )

                    if moderator:
                        description += f"**Timed out by:** {moderator.mention}"

                    embed = create_embed(
                        title="Member Timed Out",
                        description=description,
                        color=discord.Color.orange(),
                        footer=f"User ID: {after.id}",
                        timestamp=True,
                    )

                    await self.send_log(channel, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """
        Handle member removal - could be leave or kick.

        Waits briefly to check if it was a ban (on_member_ban fires shortly after).
        Uses audit logs to determine if it was a kick or voluntary leave.
        """
        logger.debug(f"on_member_remove fired in guild {member.guild.id} for {member.id}")

        if not await is_cog_enabled(member.guild.id, "action_log"):
            return

        # Wait briefly to see if ban event fires
        await asyncio.sleep(0.5)

        # Check if this was a ban (on_member_ban would have fired by now)
        if hasattr(self, "recent_bans") and (member.guild.id, member.id) in self.recent_bans:
            # Skip - ban event will handle logging
            del self.recent_bans[(member.guild.id, member.id)]
            return

        # Check audit logs to determine if it was a kick
        moderator, _ = await self.get_moderator_from_audit_log(
            member.guild, discord.AuditLogAction.kick, member.id, seconds=5, max_attempts=2
        )

        removal_type = "kick" if moderator else "leave"

        # Get cached member info
        cached = await self.get_cached_member(member.guild.id, member.id)
        if not cached:
            logger.warning(f"No cached info for member {member.id} in guild {member.guild.id}")
            return

        # Get cached roles
        roles = await self.get_cached_roles(member.guild.id, member.id)
        roles_text = ", ".join(f"`{r['role_name']}`" for r in roles) or "None"

        # Calculate time in server
        time_in_server = datetime.now(timezone.utc) - cached["joined_at"]
        days = time_in_server.days

        # Build embed based on removal type
        if removal_type == "kick":
            _, channel = await self.get_log_setup(member.guild, "moderation_events", "kick")
            title = "Member Kicked"
            color = discord.Color.red()
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

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """
        Handle member ban with moderator tracking.

        Tracks recent bans to prevent double-logging with on_member_remove.
        """
        logger.debug(f"on_member_ban fired in guild {guild.id} for {user.id}")

        # Track recent ban to avoid double logging in on_member_remove
        if not hasattr(self, "recent_bans"):
            self.recent_bans = {}

        self.recent_bans[(guild.id, user.id)] = datetime.now(timezone.utc)

        # Clean up old entries (older than 5 seconds)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.recent_bans = {k: v for k, v in self.recent_bans.items() if v > cutoff}

        channel = await self.validate_event(guild, "moderation_events", "ban")
        if not channel:
            return

        # Get who performed the ban
        moderator, reason = await self.get_moderator_from_audit_log(
            guild, discord.AuditLogAction.ban, user.id, seconds=5
        )

        # Get cached member info if available
        cached = await self.get_cached_member(guild.id, user.id)

        description = f"**User:** {user.mention}\n"

        if reason:
            description += f"**Reason:** {reason}\n"

        if moderator:
            description += f"**Banned by:** {moderator.mention}\n"

        if cached:
            roles = await self.get_cached_roles(guild.id, user.id)
            roles_text = ", ".join(f"`{r['role_name']}`" for r in roles) or "None"

            description += f"**Joined:** <t:{int(cached['joined_at'].timestamp())}:R>\n" f"**Roles:** {roles_text}"

        embed = create_embed(
            title="Member Banned",
            description=description,
            color=discord.Color.dark_red(),
            footer=f"User ID: {user.id}",
            timestamp=True,
        )

        await self.send_log(channel, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        """Handle member unban with moderator tracking."""
        channel = await self.validate_event(guild, "moderation_events", "unban", "on_member_unban")
        if not channel:
            return

        # Get who unbanned the user
        moderator, _ = await self.get_moderator_from_audit_log(guild, discord.AuditLogAction.unban, user.id, seconds=5)

        description = f"**User:** {user.mention}\n"

        if moderator:
            description += f"**Unbanned by:** {moderator.mention}"

        embed = create_embed(
            title="Member Unbanned",
            description=description,
            color=discord.Color.green(),
            footer=f"User ID: {user.id}",
            timestamp=True,
        )

        await self.send_log(channel, embed)

    # ----------------------------
    # ROLE EVENTS
    # ----------------------------

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        """Handle role creation with moderator tracking."""

        # Validate event and get log channel
        log_channel = await self.validate_event(role.guild, "role_events", "create", "on_guild_role_create")
        if not log_channel:
            return

        # Get who created the role
        moderator, _ = await self.get_moderator_from_audit_log(
            role.guild,
            discord.AuditLogAction.role_create,
            role.id,
            seconds=5,
        )

        # Build description
        description = (
            f"**Role:** {role.mention}\n"
            f"**Color:** {role.color}\n"
            f"**Hoisted:** {'Yes' if role.hoist else 'No'}\n"
            f"**Mentionable:** {'Yes' if role.mentionable else 'No'}\n"
            f"**ID:** {role.id}\n"
        )

        if moderator:
            description += f"**Created by:** {moderator.mention}"

        embed = create_embed(
            title="Role Created",
            description=description,
            color=role.color if role.color != discord.Color.default() else discord.Color.green(),
            footer=f"Role ID: {role.id}",
            timestamp=True,
        )
        await self.send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Handle role deletion with moderator tracking."""

        # Validate event and get log channel
        log_channel = await self.validate_event(role.guild, "role_events", "delete", "on_guild_role_delete")
        if not log_channel:
            return

        # Get who deleted the role
        moderator, _ = await self.get_moderator_from_audit_log(
            role.guild,
            discord.AuditLogAction.role_delete,
            role.id,
            seconds=5,
        )

        # Build description
        description = f"**Role Name:** {role.name}\n" f"**Color:** {role.color}\n" f"**ID:** {role.id}\n"

        if moderator:
            description += f"**Deleted by:** {moderator.mention}"

        embed = create_embed(
            title="Role Deleted",
            description=description,
            color=role.color if role.color != discord.Color.default() else discord.Color.red(),
            footer=f"Role ID: {role.id}",
            timestamp=True,
        )

        await self.send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """
        Handle role updates with single audit log check.

        Logs:
        - Name changes
        - Color changes
        - Permission changes
        - Hoisted changes (display separately)
        - Mentionable changes
        """

        # Early cog check
        if not await is_cog_enabled(after.guild.id, "action_log"):
            return

        logger.debug(f"on_guild_role_update fired in guild {after.guild.id}")

        # ✅ Get moderator ONCE at the top - covers all role changes
        moderator, _ = await self.get_moderator_from_audit_log(
            after.guild,
            discord.AuditLogAction.role_update,
            after.id,
            seconds=5,
        )

        # ----------------------------
        # NAME CHANGE
        # ----------------------------
        if before.name != after.name:
            _, log_channel = await self.get_log_setup(after.guild, "role_events", "update")
            if log_channel:
                description = (
                    f"**Role:** {after.mention}\n" f"**Old Name:** {before.name}\n" f"**New Name:** {after.name}\n"
                )

                if moderator:
                    description += f"**Changed by:** {moderator.mention}"

                embed = create_embed(
                    title="Role Name Changed",
                    description=description,
                    color=after.color if after.color != discord.Color.default() else discord.Color.blue(),
                    footer=f"Role ID: {after.id}",
                    timestamp=True,
                )

                await self.send_log(log_channel, embed)

        # ----------------------------
        # COLOR CHANGE
        # ----------------------------
        if before.color != after.color:
            _, log_channel = await self.get_log_setup(after.guild, "role_events", "update")
            if log_channel:
                # Format colors as hex
                old_color_hex = f"#{before.color.value:06x}" if before.color.value else "Default"
                new_color_hex = f"#{after.color.value:06x}" if after.color.value else "Default"

                description = (
                    f"**Role:** {after.mention}\n"
                    f"**Old Color:** {old_color_hex}\n"
                    f"**New Color:** {new_color_hex}\n"
                )

                if moderator:
                    description += f"**Changed by:** {moderator.mention}"

                embed = create_embed(
                    title="Role Color Changed",
                    description=description,
                    color=after.color if after.color != discord.Color.default() else discord.Color.blue(),
                    footer=f"Role ID: {after.id}",
                    timestamp=True,
                )

                await self.send_log(log_channel, embed)

        # ----------------------------
        # PERMISSION CHANGE
        # ----------------------------
        if before.permissions != after.permissions:
            _, log_channel = await self.get_log_setup(after.guild, "role_events", "update")
            if log_channel:
                description = f"**Role:** {after.mention}\n" f"**Change:** Permissions updated\n"

                if moderator:
                    description += f"**Changed by:** {moderator.mention}\n"

                description += f"\n*Check audit log for detailed permission changes*"

                embed = create_embed(
                    title="Role Permissions Changed",
                    description=description,
                    color=discord.Color.orange(),
                    footer=f"Role ID: {after.id}",
                    timestamp=True,
                )

                await self.send_log(log_channel, embed)

        # ----------------------------
        # HOISTED CHANGE (Display Separately)
        # ----------------------------
        if before.hoist != after.hoist:
            _, log_channel = await self.get_log_setup(after.guild, "role_events", "update")
            if log_channel:
                status = "enabled" if after.hoist else "disabled"

                description = f"**Role:** {after.mention}\n" f"**Display Separately:** {status.capitalize()}\n"

                if moderator:
                    description += f"**Changed by:** {moderator.mention}"

                embed = create_embed(
                    title=f"Role Hoisting {status.capitalize()}",
                    description=description,
                    color=after.color if after.color != discord.Color.default() else discord.Color.blue(),
                    footer=f"Role ID: {after.id}",
                    timestamp=True,
                )

                await self.send_log(log_channel, embed)

        # ----------------------------
        # MENTIONABLE CHANGE
        # ----------------------------
        if before.mentionable != after.mentionable:
            _, log_channel = await self.get_log_setup(after.guild, "role_events", "update")
            if log_channel:
                status = "enabled" if after.mentionable else "disabled"

                description = f"**Role:** {after.mention}\n" f"**Mentionable:** {status.capitalize()}\n"

                if moderator:
                    description += f"**Changed by:** {moderator.mention}"

                embed = create_embed(
                    title=f"Role Mentionable {status.capitalize()}",
                    description=description,
                    color=after.color if after.color != discord.Color.default() else discord.Color.blue(),
                    footer=f"Role ID: {after.id}",
                    timestamp=True,
                )

                await self.send_log(log_channel, embed)

    # ----------------------------
    # Channel Events
    # ----------------------------

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """Handle channel creation events."""
        log_channel = await self.validate_event(channel.guild, "channel_events", "create", "on_guild_channel_create")
        if not log_channel:
            return

        moderator, _ = await self.get_moderator_from_audit_log(
            channel.guild,
            discord.AuditLogAction.channel_create,
            channel.id,
            seconds=5,
        )

        # Dtermine channel type
        if isinstance(channel, discord.TextChannel):
            channel_type = "Text Channel"
        elif isinstance(channel, discord.VoiceChannel):
            channel_type = "Voice Channel"
        elif isinstance(channel, discord.CategoryChannel):
            channel_type = "Category"
        elif isinstance(channel, discord.ForumChannel):
            channel_type = "Forum Channel"
        elif isinstance(channel, discord.StageChannel):
            channel_type = "Stage Channel"
        else:
            channel_type = "Channel"

        # Build description
        description = f"**Channel:** {channel.mention}\n" f"**Type:** {channel_type}\n" f"**ID:** {channel.id}\n"

        # Add category info if applicable
        if hasattr(channel, "category") and channel.category:
            description += f"**Category:** `{channel.category.name}`\n"

        if moderator:
            description += f"**Created by:** {moderator.mention}"

        embed = create_embed(
            title="Channel Created",
            description=description,
            color=discord.Color.green(),
            footer=f"Channel ID: {channel.id}",
            timestamp=True,
        )
        await self.send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Handle channel deletion events."""
        log_channel = await self.validate_event(channel.guild, "channel_events", "delete", "on_guild_channel_delete")
        if not log_channel:
            return

        moderator, _ = await self.get_moderator_from_audit_log(
            channel.guild,
            discord.AuditLogAction.channel_delete,
            channel.id,
            seconds=5,
        )

        # Determine channel type
        if isinstance(channel, discord.TextChannel):
            channel_type = "Text Channel"
        elif isinstance(channel, discord.VoiceChannel):
            channel_type = "Voice Channel"
        elif isinstance(channel, discord.CategoryChannel):
            channel_type = "Category"
        elif isinstance(channel, discord.ForumChannel):
            channel_type = "Forum Channel"
        elif isinstance(channel, discord.StageChannel):
            channel_type = "Stage Channel"
        else:
            channel_type = "Channel"

        # Build description
        description = f"**Channel:** {channel.mention}\n" f"**Type:** {channel_type}\n" f"**ID:** {channel.id}\n"

        # Add category info if applicable
        if hasattr(channel, "category") and channel.category:
            description += f"\n**Category:** `{channel.category.name}`"

        if moderator:
            description += f"**Deleted by:** {moderator.mention}"

        embed = create_embed(
            title="Channel Deleted",
            description=description,
            color=discord.Color.red(),
            footer=f"**Channel ID:** {channel.id}",
            timestamp=True,
        )
        await self.send_log(log_channel, embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        """
        Handle channel updates.

        Logs:
        - Name changes (all channel types)
        - Topic changes (text channels only)
        - NSFW changes (text channels only)
        - Slowmode changes (text channels only)
        - Permission overwrites changes (all channel types)
        - Category changes (all channel types except categories)
        """
        log_channel = await self.validate_event(after.guild, "channel_events", "update", "on_guild_channel_update")
        if not log_channel:
            return

        moderator, _ = await self.get_moderator_from_audit_log(
            after.guild, discord.AuditLogAction.channel_update, after.id, seconds=5
        )

        # -- NAME CHANGE --
        if before.name != after.name:
            description = f"**Channel:** {after.mention}\n" f"**Change:** Name\n"

            if moderator:
                description += f"**Changed by:** {moderator.mention}\n\n"

            description += f"**Old Name:** {before.name}\n" f"**New Name:** {after.name}\n"

            embed = create_embed(
                title="Channel Update",
                description=description,
                color=discord.Color.blue(),
                footer=f"Channel ID: {after.id}",
                timestamp=True,
            )

            await self.send_log(log_channel, embed)

        # # --- TEXT CHANNEL SPECIFIC ---
        # if isinstance(after, discord.TextChannel):
        #     if before.topic != after.topic:
        #         # ... log topic change ...

        #     if before.nsfw != after.nsfw:
        #         # ... log NSFW change ...

        #     if before.slowmode_delay != after.slowmode_delay:
        #         # ... log slowmode change ...

        # -- PERMISSIONS --
        if before.overwrites != after.overwrites:
            description = f"**Channel:** {after.mention}\n" f"**Change:** Permissions\n"
            if moderator:
                description += f"**Changed by:** {moderator.mention}\n"

            description += f"\n*Check audit log for detailed permission changes*"

            embed = create_embed(
                title="Channel Updated",
                description=description,
                color=discord.Color.blue(),
                footer=f"Channel ID: {after.id}",
                timestamp=True,
            )
            await self.send_log(log_channel, embed)

        # -- CATEGORY CHANGE --
        if hasattr(after, "category") and before.category != after.category:
            description = f"**Channel:** {after.mention}\n" f"**Change:** Category\n"

            if moderator:
                description += f"**Changed by:** {moderator.mention} ({moderator.id})\n\n"

            description += (
                f"**Old Category:** {before.category.mention}\n" f"**New Category:** {after.category.mention}\n"
            )

            embed = create_embed(
                title="Channel Updated",
                description=description,
                color=discord.Color.blue(),
                footer=f"Channel ID: {after.id}",
                timestamp=True,
            )
            await self.send_log(log_channel, embed)

    # ----------------------------
    # Emoji Events
    # ----------------------------

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: Sequence[discord.Emoji],
        after: Sequence[discord.Emoji],
    ):
        """Handle emoji create/delete/rename."""
        if not await is_cog_enabled(guild.id, "action_log"):
            return

        logger.debug(f"on_guild_emojis_update fired in guild {guild.id}")

        before_ids = {emoji.id for emoji in before}
        after_ids = {emoji.id for emoji in after}

        # Check for created emojis
        created_ids = after_ids - before_ids
        if created_ids:
            _, channel = await self.get_log_setup(guild, "emoji_events", "create")
            if channel:
                for emoji in after:
                    if emoji.id in created_ids:
                        embed = create_embed(
                            title="Emoji Created",
                            description=(
                                f"**Emoji:** {emoji}\n"
                                f"**Name:** {emoji.name}\n"
                                f"**Animated:** {'Yes' if emoji.animated else 'No'}\n"
                                f"**ID:** {emoji.id}"
                            ),
                            color=discord.Color.green(),
                            footer=f"Emoji ID: {emoji.id}",
                            timestamp=True,
                        )
                        await self.send_log(channel, embed)

        # Check for deleted emojis
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

        # Check for renamed emojis
        for old_emoji in before:
            if old_emoji.id in after_ids:
                new_emoji = discord.utils.get(after, id=old_emoji.id)
                if new_emoji and old_emoji.name != new_emoji.name:
                    _, channel = await self.get_log_setup(guild, "emoji_events", "name_change")
                    if channel:
                        embed = create_embed(
                            title="Emoji Name Changed",
                            description=(
                                f"**Emoji:** {new_emoji}\n"
                                f"**Old Name:** {old_emoji.name}\n"
                                f"**New Name:** {new_emoji.name}\n"
                                f"**ID:** {new_emoji.id}"
                            ),
                            color=discord.Color.orange(),
                            footer=f"Emoji ID: {new_emoji.id}",
                            timestamp=True,
                        )
                        await self.send_log(channel, embed)

    # ----------------------------
    # Voice Events
    # ----------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """
        Handle voice channel events (join, leave, move).

        For moves, attempts to determine if user moved themselves or was moved by a moderator.
        """
        if not await is_cog_enabled(member.guild.id, "action_log"):
            return

        logger.debug(f"on_voice_state_update fired in guild {member.guild.id}")

        # Voice Join
        if before.channel is None and after.channel is not None:
            _, channel = await self.get_log_setup(member.guild, "voice_events", "join")
            if channel:
                embed = create_embed(
                    title="Voice Channel Join",
                    description=(f"**User:** {member.mention}\n" f"**Channel:** {after.channel.mention}"),
                    color=discord.Color.green(),
                    footer=f"User ID: {member.id} | Channel ID: {after.channel.id}",
                    timestamp=True,
                )
                await self.send_log(channel, embed)

        # Voice Leave
        elif before.channel is not None and after.channel is None:
            _, channel = await self.get_log_setup(member.guild, "voice_events", "leave")
            if channel:
                embed = create_embed(
                    title="Voice Channel Leave",
                    description=(f"**User:** {member.mention}\n" f"**Channel:** {before.channel.mention}"),
                    color=discord.Color.red(),
                    footer=f"User ID: {member.id} | Channel ID: {before.channel.id}",
                    timestamp=True,
                )
                await self.send_log(channel, embed)

        # Voice Move
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            _, channel = await self.get_log_setup(member.guild, "voice_events", "move")
            if channel:
                # Check who moved them (with retries for audit log delay)
                moderator, _ = await self.get_moderator_from_audit_log(
                    member.guild,
                    discord.AuditLogAction.member_move,
                    member.id,
                    max_attempts=2,
                    retry_delay=0.2,
                )

                # Build description
                description_parts = [
                    f"**User:** {member.mention}",
                    f"**Channel:** {before.channel.mention} → {after.channel.mention}",
                ]

                # Add mover info if found
                if moderator:
                    if moderator.id == member.id:
                        description_parts.append(f"**Moved by:** Self")
                    else:
                        description_parts.append(f"**Moved by:** {moderator.mention}")

                description = "\n".join(description_parts)

                embed = create_embed(
                    title="Voice Channel Move",
                    description=description,
                    color=discord.Color.blue(),
                    footer=f"User ID: {member.id}",
                    timestamp=True,
                )
                await self.send_log(channel, embed)


async def setup(bot: commands.Bot):
    """Load the ActionLog cog."""
    await bot.add_cog(ActionLog(bot))
