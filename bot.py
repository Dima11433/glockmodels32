import asyncio
import logging
import os
import sys

# Гарантируем, что текущая директория бота добавлена в sys.path для импорта handlers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import datetime
from aiogram import Bot, Dispatcher
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import load_config
from db import Database
from handlers import admin, ads, buy, checks_promos, user_basic
from handlers.buy import notify_payment_result
from middleware import UpsertUserMiddleware
from payments import Payments, apply_paid_invoice
import photo_manager


async def ads_scheduler(bot: Bot, db: Database) -> None:
    """Фоновая задача: рассылка забронированных постов и снятие истекших кнопок."""
    while True:
        try:
            now = datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M")

            # Деактивируем истекшие слоты
            await db.expire_old_ads()

            # Проверяем рассылки
            due = await db.get_due_mailings()
            for ad in due:
                if ad["slot_date"] == today_str and ad["slot_time"] <= time_str:
                    logging.info(f"🚀 Запуск автоматической рассылки #{ad['id']}...")
                    
                    cur = await db.conn.execute("SELECT id FROM users")
                    users = await cur.fetchall()

                    markup = None
                    if ad["has_button"] and ad["button_title"] and ad["button_url"]:
                        markup = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=ad["button_title"], url=ad["button_url"])]
                        ])

                    sent = 0
                    for u in users:
                        try:
                            if ad["photo_file_id"]:
                                await bot.send_photo(chat_id=u["id"], photo=ad["photo_file_id"], caption=ad["text_content"], reply_markup=markup, parse_mode="HTML")
                            else:
                                await bot.send_message(chat_id=u["id"], text=ad["text_content"], reply_markup=markup, parse_mode="HTML")
                            sent += 1
                            await asyncio.sleep(0.05)
                        except Exception:
                            pass
                    
                    await db.mark_ad_completed(ad["id"])
                    logging.info(f"✅ Рассылка #{ad['id']} завершена! Доставлено: {sent}/{len(users)}")
        except Exception:
            logging.exception("Ошибка в ads_scheduler")
        await asyncio.sleep(30)


async def invoice_watcher(bot: Bot, db: Database, payments: Payments, config) -> None:
    while True:
        try:
            await db.release_expired()
            if payments.enabled:
                active = await db.list_active_invoices()
                if active:
                    statuses = await payments.get_statuses(active)
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


async def start_dummy_webserver():
    """Фоновый HTTP сервер для бесплатного тарифа Render (Web Service), слушающий $PORT."""
    port_str = os.getenv("PORT")
    if not port_str:
        return
    try:
        port = int(port_str)
        async def handle(reader, writer):
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        await asyncio.start_server(handle, "0.0.0.0", port)
        logging.info(f"🌐 Dummy Web Server запущен на порту {port} для Render Free Tier")
    except Exception as e:
        logging.warning(f"Не удалось запустить dummy webserver: {e}")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    db_path = os.getenv("DB_PATH", "shop.db")
    db = Database(db_path)
    await db.connect()
    payments = Payments(config.cryptopay_token, config.cryptopay_testnet, config.xrocket_api_key)
    main_bot = Bot(config.bot_token)
    dp = Dispatcher()
    dp["db"] = db
    dp["config"] = config
    dp["payments"] = payments
    dp["bot"] = main_bot
    dp.message.outer_middleware(UpsertUserMiddleware())
    dp.callback_query.outer_middleware(UpsertUserMiddleware())
    
    # ОСНОВНОЙ БОТ: базовая функциональность + реклама + чеки + промо + покупки + админка
    dp.include_routers(admin.router, checks_promos.router, ads.router, buy.router, user_basic.router)

    # Запускаем миграцию фото и планировщики в фоне
    try:
        asyncio.create_task(photo_manager.migrate_photos(main_bot, db))
        asyncio.create_task(ads_scheduler(main_bot, db))
    except Exception:
        logging.exception("Failed to start background tasks")

    await start_dummy_webserver()
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
