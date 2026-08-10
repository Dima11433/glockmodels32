import asyncio
import traceback

from config import load_config
from db import Database
from photo_manager import migrate_photos
from aiogram import Bot


async def main():
    try:
        cfg = load_config()
    except Exception as e:
        print('Failed to load config:', e)
        return

    bot = Bot(cfg.bot_token)
    db = Database('shop.db')
    await db.connect()

    try:
        print('Starting photo migration...')
        migrated = await migrate_photos(bot, db)
        print(f'Migration finished. Migrated: {migrated}')
    except Exception as e:
        print('Migration failed:')
        traceback.print_exc()
    finally:
        try:
            await bot.close()
        except Exception:
            pass
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
