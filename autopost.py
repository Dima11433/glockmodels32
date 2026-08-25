import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from db import Database
import texts


async def send_product_autopost(bot: Bot, db: Database, product_id: int, config) -> bool:
    """Отправляет пост о новом товаре / пополнении в канал обновлений."""
    try:
        enabled = await db.get_setting("autopost:enabled")
        if enabled == "0":
            logging.info("Автопостинг выключен в настройках.")
            return False

        p = await db.get_product(product_id)
        if not p:
            return False

        channel_id_str = await db.get_setting("autopost:channel_id")
        channel_id = int(channel_id_str) if channel_id_str else config.update_channel_id

        bot_user = await bot.get_me()
        bot_username = bot_user.username or config.bot_username

        # Текст поста
        desc = p["description"].strip() if p.get("description") else ""
        desc_block = f"\n\n📝 <b>Описание:</b>\n{desc}" if desc else ""
        
        caption = (
            f"🔥 <b>НОВОЕ ПОСТУПЛЕНИЕ В МАГАЗИНЕ!</b>\n\n"
            f"📦 <b>Товар:</b> {p['name']}\n"
            f"💵 <b>Цена:</b> {texts.fmt_usd(p['price'])}"
            f"{desc_block}\n\n"
            f"⚡️ <i>Нажмите кнопку ниже для быстрой покупки:</i>"
        )

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍️ Купить в магазине", url=f"https://t.me/{bot_username}?start=prod_{p['id']}")],
            [InlineKeyboardButton(text="🤖 Открыть магазин", url=f"https://t.me/{bot_username}")]
        ])

        # Ищем фото товара
        photos = await db.get_product_photos(product_id)
        if photos and len(photos) > 0:
            photo_file_id = photos[0]["file_id"]
            await bot.send_photo(chat_id=channel_id, photo=photo_file_id, caption=caption, reply_markup=markup, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=channel_id, text=caption, reply_markup=markup, parse_mode="HTML")

        logging.info(f"✅ Автопостинг товара '{p['name']}' отправлен в канал {channel_id}")
        return True
    except Exception as e:
        logging.warning(f"Не удалось отправить автопост в канал: {e}")
        return False
