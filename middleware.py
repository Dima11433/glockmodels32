from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, TelegramObject, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# Обязательный канал для главного бота (жёстко зафиксирован)
MAIN_CHANNEL_USERNAME = "news_glock_shop"
MAIN_CHANNEL_LINK = "https://t.me/news_glock_shop"

# Callback data которые НЕ блокируются проверкой подписки
SKIP_SUBSCRIPTION_DATA = {"check_subscription", "check_mirror_subscription"}


class UpsertUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user and not user.is_bot:
            db = data["db"]
            config = data["config"]
            bot = data.get("bot")

            # Определяем токен текущего бота
            current_token = bot.token if bot else None
            mirror = None
            if current_token:
                mirror = await db.get_mirror_by_token(current_token)
                if mirror:
                    data["mirror"] = mirror
                    await db.register_mirror_user(user.id, mirror["id"])

            # Получаем или создаём пользователя
            existing_user = await db.get_user(user.id)
            user_obj = await db.get_or_create_user(user.id, user.username)

            # Логируем нового пользователя
            if not existing_user and user_obj:
                await db.add_log(user.id, user.username, "новый_пользователь",
                                 f"Присоединился @{user.username}" + (f" через зеркало #{mirror['id']}" if mirror else ""))
                if bot and config.admin_group_id:
                    try:
                        await bot.send_message(
                            config.admin_group_id,
                            f"👤 Новый пользователь!\n"
                            f"ID: {user.id}\n"
                            f"Username: @{user.username or 'не указан'}\n"
                            f"Ссылка: tg://user?id={user.id}"
                        )
                    except Exception:
                        pass

            # Сохраняем admin_id
            if user.username and user.username.lower() == config.admin_username.lower():
                await db.set_setting("admin_id", str(user.id))

            # --- Проверка подписки ---
            # Пропускаем проверку для callback check_subscription
            is_check_cb = (
                isinstance(event, CallbackQuery)
                and event.data in SKIP_SUBSCRIPTION_DATA
            )
            is_start_cmd = (
                isinstance(event, Message)
                and (event.text or "").startswith("/start")
            )

            if not is_check_cb and not is_start_cmd and bot:
                if mirror:
                    # Зеркало: проверяем канал зеркала (если задан)
                    ch_username = mirror["channel_username"] if mirror["channel_username"] else None
                    ch_link = mirror["channel_link"] if mirror["channel_link"] else None
                else:
                    # Главный бот: жёстко проверяем @news_glock_shop
                    ch_username = MAIN_CHANNEL_USERNAME
                    ch_link = MAIN_CHANNEL_LINK

                if ch_username and ch_link:
                    try:
                        member = await bot.get_chat_member(f"@{ch_username}", user.id)
                        is_subscribed = member.status in ("member", "administrator", "creator")
                    except Exception:
                        is_subscribed = True  # При ошибке API не блокируем

                    if not is_subscribed:
                        markup = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="📢 Подписаться на канал", url=ch_link)],
                            [InlineKeyboardButton(text="✅ Я подписался",
                                                  callback_data="check_subscription" if not mirror else "check_mirror_subscription")],
                        ])
                        text = (
                            f"📢 <b>Для доступа к боту необходима подписка!</b>\n\n"
                            f"🔗 Подпишитесь на наш канал и нажмите кнопку ниже:"
                        )
                        if isinstance(event, Message):
                            await event.answer(text, reply_markup=markup, parse_mode="HTML")
                        elif isinstance(event, CallbackQuery):
                            await event.message.answer(text, reply_markup=markup, parse_mode="HTML")
                            await event.answer()
                        return  # Блокируем обработку

        return await handler(event, data)
