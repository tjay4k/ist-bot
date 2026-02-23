import asyncio
import logging
from logging.handlers import RotatingFileHandler
import sys
import os
from dotenv import load_dotenv
from core.bot import ISTBot

# ---------- Load environment variables ----------

load_dotenv("config/.env")

# ---------- Setup logging ----------


def setup_logging(mode: str):
    level = logging.DEBUG if mode == "debug" else logging.INFO

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    os.makedirs("logs", exist_ok=True)

    file_handler = RotatingFileHandler(
        "logs/bot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=[console_handler, file_handler])

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)

# ---------- Launch script ----------


async def main():
    # default = production
    mode = sys.argv[1] if len(sys.argv) > 1 else "prod"

    setup_logging(mode)

    if mode == "prod":
        token = os.getenv("DISCORD_TOKEN_PROD")
    elif mode == "dev":
        token = os.getenv("DISCORD_TOKEN_DEV")
    elif mode == "debug":
        token = os.getenv("DISCORD_TOKEN_DEV")
    else:
        raise RuntimeError(f"Invalid mode, available modes: 'prod' & 'dev'")

    if not token:
        raise RuntimeError(f"Token missing for mode: {mode}")

    bot = ISTBot(mode=mode)

    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
