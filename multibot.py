import asyncio
import logging
from aiogram import Bot, Dispatcher

from middleware import UpsertUserMiddleware
from handlers import admin, buy, user, checks_promos, admin_mirror

logger = logging.getLogger(__name__)


class MultiBotManager:
    def __init__(self, dp: Dispatcher, main_bot: Bot, db, config, payments):
        self.dp = dp
        self.main_bot = main_bot
        self.db = db
        self.config = config
        self.payments = payments
        self.active_bots: dict[int, tuple[Bot, asyncio.Task]] = {}

    async def start(self):
        """Запуск главного бота и всех активных зеркал из базы"""
        logger.info("Запуск системы Мультиботов (Main Bot + Zerkala)...")
        mirrors = await self.db.list_active_mirrors()
        for mirror in mirrors:
            await self.start_mirror_bot(mirror)

    async def start_mirror_bot(self, mirror: dict):
        mirror_id = mirror["id"]
        token = mirror["bot_token"]
        if mirror_id in self.active_bots:
            return

        try:
            bot = Bot(token=token)
            task = asyncio.create_task(self.dp.start_polling(bot, handle_signals=False))
            self.active_bots[mirror_id] = (bot, task)
            logger.info(f"Зеркало #{mirror_id} (@{mirror['bot_username']}) успешно запущено.")
        except Exception as e:
            logger.error(f"Не удалось запустить бот-зеркало #{mirror_id}: {e}")

    async def stop_all(self):
        for mirror_id, (bot, task) in list(self.active_bots.items()):
            task.cancel()
            await bot.session.close()
        self.active_bots.clear()
