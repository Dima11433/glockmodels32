import asyncio
import logging
import os

from aiogram import Bot, Dispatcher

from config import load_config
from db import Database
from handlers import admin, buy, checks_promos
from handlers import user_basic
from handlers.buy import notify_payment_result
from middleware import UpsertUserMiddleware
from payments import Payments, apply_paid_invoice
import photo_manager


async def invoice_watcher(bot: Bot, db: Database, payments: Payments, config) -> None:
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
                                await notify_payment_result(bot, db, result, config)
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
    db_path = os.getenv("DB_PATH", "shop.db")
    db = Database(db_path)
    await db.connect()
    payments = Payments(config.cryptopay_token, config.cryptopay_testnet)
    main_bot = Bot(config.bot_token)
    dp = Dispatcher()
    dp["db"] = db
    dp["config"] = config
    dp["payments"] = payments
    dp["bot"] = main_bot
    dp.message.outer_middleware(UpsertUserMiddleware())
    dp.callback_query.outer_middleware(UpsertUserMiddleware())
    
    # ОСНОВНОЙ БОТ: базовая функциональность + чеки + промо + мини приложение (БЕЗ ЗЕРКАЛ)
    dp.include_routers(admin.router, checks_promos.router, buy.router, user_basic.router)

    # Запускаем миграцию фото в фоне (чтобы не блокировать старт бота)
    try:
        asyncio.create_task(photo_manager.migrate_photos(main_bot, db))
    except Exception:
        logging.exception("Failed to start photo migration")

    watcher = asyncio.create_task(invoice_watcher(main_bot, db, payments, config))
    logging.info("✅ ОСНОВНОЙ БОТ запуск (с чеками, промо)")

    # ── Стартовое уведомление в админ-группу ──
    try:
        import sys
        from datetime import datetime, timezone, timedelta
        me = await main_bot.get_me()
        now = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M:%S")
        await main_bot.send_message(
            config.admin_group_id,
            f"✅ <b>Бот запущен!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 @{me.username} (<code>{me.id}</code>)\n"
            f"🕐 Время: <b>{now} МСК</b>\n"
            f"🐍 Python {sys.version.split()[0]}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📡 Polling активен, жду покупки!",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.warning(f"Не удалось отправить стартовое сообщение: {e}")
    # ──────────────────────────────────────────

    try:
        # Robust polling loop: restart on unexpected errors with backoff
        while True:
            try:
                await dp.start_polling(main_bot)
                logging.info("Polling stopped normally")
                break
            except asyncio.CancelledError:
                logging.info("Polling cancelled, exiting")
                break
            except Exception:
                logging.exception("Polling crashed, restarting in 5s")
                await asyncio.sleep(5)
    finally:
        watcher.cancel()
        await payments.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
