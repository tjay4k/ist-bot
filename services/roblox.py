import aiohttp
import asyncio
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class RobloxService:
    def __init__(self):
        self.request_timeout = 1
        self.badge_fetch_delay = 0.1
        self.session = None

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("Roblox service session closed")

    async def fetch_user_data(self, user_id: int):
        """Fetch comprehensive Roblox user data by user ID."""
        session = await self.get_session()
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)

        try:
            # Get user info
            async with session.get(f"https://users.roblox.com/v1/users/{user_id}", timeout=timeout) as res:
                if res.status == 404:
                    raise Exception(f"Roblox user with ID {user_id} not found (404)")
                if res.status != 200:
                    raise Exception(f"Failed to fetch user info: status {res.status}")
                data = await res.json()
                username = data.get("name")
                display_name = data.get("displayName")
                created_str = data.get("created")
                is_banned = data.get("isBanned", False)

                if not username or not created_str:
                    raise Exception(f"Invalid user data for Roblox ID {user_id}")
                created_date = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                account_age_days = (datetime.now(timezone.utc) - created_date).days

            # Check inventory visibility
            inventory_visible = True
            async with session.get(
                f"https://inventory.roblox.com/v1/users/{user_id}/can-view-inventory", timeout=timeout
            ) as res:
                if res.status == 200:
                    data = await res.json()
                    inventory_visible = data.get("canView", False)
                else:
                    logger.warning(f"Failed to check inventory visibility for user {user_id}: {res.status}")
                    inventory_visible = False

            # Get social counts
            followers = await self._fetch_social_count(user_id, "followers", timeout)
            following = await self._fetch_social_count(user_id, "followings", timeout)
            friends = await self._fetch_social_count(user_id, "friends", timeout)

            # Get badges (only if inventory is visible)
            if inventory_visible:
                badges, badge_count = await self._fetch_user_badges(user_id)
                badge_pages = (badge_count + 29) // 30
            else:
                badges = []
                badge_count = None  # None indicates hidden
                badge_pages = None

            # Get username history
            previous_usernames = await self.fetch_username_history(user_id)

            # Get premium status
            has_premium = await self.fetch_premium_status(user_id)

            return {
                "username": username,
                "display_name": display_name,
                "user_id": user_id,
                "account_age_days": account_age_days,
                "account_created_date": created_date,
                "followers": followers,
                "following": following,
                "friends": friends,
                "badge_count": badge_count,  # Can be None if hidden
                "badge_pages": badge_pages,  # Can be None if hidden
                "badges": badges,
                "previous_usernames": previous_usernames,
                "has_premium": has_premium,
                "is_banned": is_banned,
                "inventory_visible": inventory_visible,
            }
        except asyncio.TimeoutError:
            raise Exception(f"Timeout fetching data for Roblox user ID {user_id}")
        except Exception:
            raise

    async def fetch_username_history(self, user_id: int) -> list[str]:
        """Fetch previous usernames for a user."""
        session = await self.get_session()
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)

        try:
            async with session.get(
                f"https://users.roblox.com/v1/users/{user_id}/username-history?limit=100&sortOrder=Desc",
                timeout=timeout,
            ) as res:
                if res.status != 200:
                    logger.warning(f"Failed to fetch username history for user {user_id}: {res.status}")
                    return []
                data = await res.json()
                usernames = [entry["name"] for entry in data.get("data", [])]
                return usernames
        except Exception as e:
            logger.error(f"Error fetching username history for user {user_id}: {e}")
            return []

    async def _fetch_social_count(self, user_id: int, endpoint: str, timeout: aiohttp.ClientTimeout) -> int:
        """Fetch followers/following/friends count."""
        session = await self.get_session()
        try:
            async with session.get(
                f"https://friends.roblox.com/v1/users/{user_id}/{endpoint}/count", timeout=timeout
            ) as res:
                if res.status == 200:
                    data = await res.json()
                    return data.get("count", 0)
                else:
                    logger.warning(f"Error fetching {endpoint} for user {user_id}: status {res.status}")
                    return 0
        except Exception as e:
            logger.error(f"Error fetching {endpoint} for user {user_id}: {e}")
            return 0

    async def _fetch_user_badges(self, user_id: int):
        """Fetch all badges for a user."""
        session = await self.get_session()
        badges = []
        badge_count = 0
        cursor = None
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)

        try:
            while True:
                url = f"https://badges.roblox.com/v1/users/{user_id}/badges?limit=100"
                if cursor:
                    url += f"&cursor={cursor}"
                async with session.get(url, timeout=timeout) as res:
                    if res.status != 200:
                        logger.error(f"Failed to fetch badges for user {user_id}: {res.status}")
                        break
                    data = await res.json()
                    badges_data = data.get("data", [])
                    badge_count += len(badges_data)
                    for badge in badges_data:
                        if "created" in badge:
                            badges.append(
                                {
                                    "name": badge["name"],
                                    "creation_date": datetime.fromisoformat(badge["created"].replace("Z", "+00:00")),
                                }
                            )
                    cursor = data.get("nextPageCursor")
                    if not cursor:
                        break
                    await asyncio.sleep(self.badge_fetch_delay)
        except Exception as e:
            logger.error(f"Error fetching badges for user {user_id}: {e}")

        return badges, badge_count

    async def fetch_user_groups(self, roblox_id: int):
        """Fetch all groups a user is in with their roles."""
        session = await self.get_session()
        url = f"https://groups.roblox.com/v1/users/{roblox_id}/groups/roles"

        try:
            async with session.get(url) as res:
                if res.status != 200:
                    raise Exception(f"Failed to fetch groups: status {res.status}")
                data = await res.json()
                groups = data.get("data", [])

                # Return list of group info
                group_list = []
                for group_info in groups:
                    group_id = group_info["group"]["id"]
                    group_name = group_info["group"]["name"]
                    role_name = group_info["role"]["name"]

                    group_list.append({"id": group_id, "name": group_name, "role": role_name})

                return group_list
        except Exception as e:
            logger.error(f"Exception fetching groups for user {roblox_id}: {e}")
            raise

    async def fetch_premium_status(self, user_id: int) -> bool:
        """Check if user has Roblox Premium."""
        session = await self.get_session()
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)

        try:
            async with session.get(
                f"https://premiumfeatures.roblox.com/v1/users/{user_id}/validate-membership", timeout=timeout
            ) as res:
                return res.status == 200
        except Exception as e:
            logger.error(f"Error checking premium status for {user_id}: {e}")
            return False


async def setup(bot):
    """Setup function to register the service with the bot."""
    roblox_service = RobloxService()
    bot.register_service("roblox", roblox_service)
    bot.roblox = roblox_service
    logger.info("Roblox service registered")