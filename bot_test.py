"""
ТЕСТ БОТ - Отдельный скрипт для новой версии с админкой для создателей зеркал
Запускать в отдельном терминале: python bot_test.py
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import load_config
from db import Database
from handlers import admin, buy, user, checks_promos, mirror_admin
from handlers.buy import notify_payment_result
from middleware import UpsertUserMiddleware
from payments import Payments, apply_paid_invoice


async def invoice_watcher(bot: Bot, db: Database, payments: Payments) -> None:
    while True:
        try:
            await db.release_expired()
            if payments.enabled:
                active = await db.list_active_invoices()
                if active:
                    statuses = await payments.get_statuses([r["invoice_id"] for r in active])
                    for row in active:
                        status = statuses.get(row["invoice_id"])
                        if status == "paid":
                            result = await apply_paid_invoice(db, row)
                            if result:
                                await notify_payment_result(bot, db, result)
                        elif status == "expired":
                            await db.mark_invoice_expired(row["invoice_id"])
                            if row["item_id"]:
                                await db.release_item(row["item_id"])
        except Exception:
            logging.exception("Ошибка фоновой проверки счетов")
        await asyncio.sleep(10)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    
    if not config.test_bot_token:
        logging.error("❌ TEST_BOT_TOKEN не настроен в .env!")
        return
    
    db = Database("shop.db")
    await db.connect()
    payments = Payments(config.cryptopay_token, config.cryptopay_testnet)
    
    test_bot = Bot(config.test_bot_token)
    dp = Dispatcher()
    dp["db"] = db
    dp["config"] = config
    dp["payments"] = payments
    dp["bot"] = test_bot
    dp.message.outer_middleware(UpsertUserMiddleware())
    dp.callback_query.outer_middleware(UpsertUserMiddleware())
    
    # ТЕСТ БОТ: новые роутеры с mirror_admin (админка для создателей зеркал)
    dp.include_routers(admin.router, checks_promos.router, mirror_admin.router, buy.router, user.router)

    watcher = asyncio.create_task(invoice_watcher(test_bot, db, payments))
    try:
        logging.info("🧪 ✅ ТЕСТ БОТ запущен!")
        await dp.start_polling(test_bot)
    finally:
        watcher.cancel()
        await payments.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
