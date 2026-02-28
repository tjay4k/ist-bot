import asyncpg
import os
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
        logger.info("Connected to PostgreSQL")

    async def close(self):
        await self.pool.close()
        logger.info("Disconnected from PostgreSQL")

    async def fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
        
    async def executemany(self, query: str, args: list):
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args)

async def setup(bot):
    db = Database()
    await db.connect()
    bot.register_service("db", db)