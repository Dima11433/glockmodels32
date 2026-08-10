"""
Админка для создателей зеркал.
Каждый создатель зеркала может управлять только своим зеркалом.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import BaseFilter, Command
from aiogram.types import TelegramObject

from db import Database
from config import Config

router = Router()


class MirrorOwnerFilter(BaseFilter):
    """Фильтр для проверки - является ли пользователь владельцем какого-либо зеркала"""
    async def __call__(self, event: TelegramObject, db: Database) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False
        mirrors = await db.get_mirrors_by_owner(user.id)
        return bool(mirrors)


class MirrorAdminState(StatesGroup):
    waiting_for_markup = State()
    waiting_for_greeting = State()
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_channel_link = State()
    waiting_for_channel_username = State()


def mirror_admin_menu_kb(mirror_id: int) -> InlineKeyboardMarkup:
    """Главное меню админки зеркала"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data=f"mirror_stats_{mirror_id}")],
        [InlineKeyboardButton(text="💰 Баланс и выплаты", callback_data=f"mirror_balance_{mirror_id}")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"mirror_settings_{mirror_id}")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data=f"mirror_mailing_{mirror_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_mirrors")],
    ])


def mirror_settings_kb(mirror_id: int) -> InlineKeyboardMarkup:
    """Меню настроек зеркала"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Приветствие", callback_data=f"mirror_greeting_{mirror_id}")],
        [InlineKeyboardButton(text="💵 Наценка", callback_data=f"mirror_markup_{mirror_id}")],
        [InlineKeyboardButton(text="📢 Подписка на канал", callback_data=f"mirror_channel_{mirror_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"mirror_admin_{mirror_id}")],
    ])


# ===== КОМАНДЫ =====

@router.message(Command("mirrors"))
async def cmd_mirrors(message: Message, db: Database):
    """Показать список своих зеркал"""
    mirrors = await db.get_mirrors_by_owner(message.from_user.id)
    if not mirrors:
        await message.answer(
            "🪞 У вас пока нет подключенных зеркал.\n\n"
            "Используйте команду /admin для добавления нового зеркала."
        )
        return

    text = "🪞 **Ваши зеркала:**\n\n"
    keyboard = []
    
    for m in mirrors:
        text += f"🤖 @{m['bot_username']}\n"
        text += f"   Наценка: {m['markup_percent']}%\n"
        text += f"   Баланс: {m['balance']} ₽\n\n"
        keyboard.append([InlineKeyboardButton(
            text=f"⚙️ Управление @{m['bot_username']}", 
            callback_data=f"mirror_admin_{m['id']}"
        )])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


# ===== ГЛАВНОЕ МЕНЮ ЗЕРКАЛА =====

@router.callback_query(F.data.startswith("mirror_admin_"))
async def mirror_admin_menu(call: CallbackQuery, db: Database):
    """Главное меню админки зеркала"""
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("❌ Доступ запрещен!", show_alert=True)
        return

    text = (
        f"⚙️ **Управление зеркалом: @{mirror['bot_username']}**\n\n"
        f"Баланс: {mirror['balance']} ₽\n"
        f"Наценка: {mirror['markup_percent']}%\n"
        f"Статус: {'✅ Активное' if mirror['is_active'] else '❌ Неактивное'}\n\n"
        f"Выберите действие:"
    )
    
    await call.message.edit_text(text, reply_markup=mirror_admin_menu_kb(mirror_id))
    await call.answer()


@router.callback_query(F.data == "back_to_mirrors")
async def back_to_mirrors(call: CallbackQuery, db: Database):
    """Вернуться к списку зеркал"""
    mirrors = await db.get_mirrors_by_owner(call.from_user.id)
    if not mirrors:
        await call.message.edit_text(
            "🪞 У вас пока нет подключенных зеркал.\n\n"
            "Используйте команду /admin для добавления нового зеркала."
        )
        await call.answer()
        return

    text = "🪞 **Ваши зеркала:**\n\n"
    keyboard = []
    
    for m in mirrors:
        text += f"🤖 @{m['bot_username']}\n"
        text += f"   Наценка: {m['markup_percent']}%\n"
        text += f"   Баланс: {m['balance']} ₽\n\n"
        keyboard.append([InlineKeyboardButton(
            text=f"⚙️ Управление @{m['bot_username']}", 
            callback_data=f"mirror_admin_{m['id']}"
        )])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await call.answer()


# ===== СТАТИСТИКА =====

@router.callback_query(F.data.startswith("mirror_stats_"))
async def mirror_stats(call: CallbackQuery, db: Database):
    """Показать статистику зеркала"""
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("❌ Доступ запрещен!", show_alert=True)
        return

    # Получаем статистику
    total_users = len(await db.get_mirror_users(mirror_id))
    
    text = (
        f"📊 **Статистика зеркала @{mirror['bot_username']}**\n\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Баланс: {mirror['balance']} ₽\n"
        f"📈 Наценка: {mirror['markup_percent']}%\n"
        f"📅 Создано: {mirror['created_at']}"
    )
    
    keyboard = [[InlineKeyboardButton(text="🔙 Назад", callback_data=f"mirror_admin_{mirror_id}")]]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await call.answer()


# ===== БАЛАНС И ВЫПЛАТЫ =====

@router.callback_query(F.data.startswith("mirror_balance_"))
async def mirror_balance(call: CallbackQuery, db: Database):
    """Показать баланс и опции выплаты"""
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("❌ Доступ запрещен!", show_alert=True)
        return

    text = (
        f"💰 **Баланс и выплаты: @{mirror['bot_username']}**\n\n"
        f"Текущий баланс: {mirror['balance']} ₽\n\n"
    )
    
    keyboard = [[InlineKeyboardButton(text="🔙 Назад", callback_data=f"mirror_admin_{mirror_id}")]]
    
    if mirror['balance'] >= 500:
        text += "✅ Вы можете запросить выплату (минимум 500 ₽)"
        keyboard.insert(0, [InlineKeyboardButton(text="💸 Запросить выплату", callback_data=f"mirror_withdraw_{mirror_id}")])
    else:
        text += f"⏳ Нужно еще {500 - mirror['balance']} ₽ для выплаты (минимум 500 ₽)"
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await call.answer()


@router.callback_query(F.data.startswith("mirror_withdraw_"))
async def mirror_withdraw(call: CallbackQuery, db: Database):
    """Запрос на выплату"""
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("❌ Доступ запрещен!", show_alert=True)
        return

    if mirror['balance'] < 500:
        await call.answer("❌ Недостаточно средств для выплаты!", show_alert=True)
        return

    # Создаем запрос на выплату
    await db.conn.execute(
        "INSERT INTO withdrawal_requests (mirror_id, owner_id, amount, requisites, status) VALUES (?, ?, ?, ?, ?)",
        (mirror_id, call.from_user.id, mirror['balance'], 'pending', 'pending')
    )
    await db.conn.commit()
    
    text = (
        f"✅ **Запрос на выплату создан!**\n\n"
        f"Сумма: {mirror['balance']} ₽\n"
        f"Статус: В ожидании обработки\n\n"
        f"Администратор свяжется с вами в ближайшее время."
    )
    
    keyboard = [[InlineKeyboardButton(text="🔙 Назад", callback_data=f"mirror_admin_{mirror_id}")]]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await call.answer()


# ===== НАСТРОЙКИ =====

@router.callback_query(F.data.startswith("mirror_settings_"))
async def mirror_settings(call: CallbackQuery, db: Database):
    """Меню настроек зеркала"""
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("❌ Доступ запрещен!", show_alert=True)
        return

    text = f"⚙️ **Настройки зеркала @{mirror['bot_username']}**"
    
    await call.message.edit_text(text, reply_markup=mirror_settings_kb(mirror_id))
    await call.answer()


# ===== ПРИВЕТСТВИЕ =====

@router.callback_query(F.data.startswith("mirror_greeting_"))
async def mirror_greeting_start(call: CallbackQuery, state: FSMContext, db: Database):
    """Начать изменение приветствия"""
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("❌ Доступ запрещен!", show_alert=True)
        return

    await state.set_state(MirrorAdminState.waiting_for_greeting)
    await state.update_data(target_mirror_id=mirror_id)
    
    text = "📝 **Введите новое приветственное сообщение**\n\n"
    if mirror['greeting_text']:
        text += f"Текущее сообщение:\n{mirror['greeting_text']}\n\n"
    text += "Поддерживается Markdown форматирование: *жирный*, _курсив_, [ссылка](url)"
    
    await call.message.answer(text)
    await call.answer()


@router.message(MirrorAdminState.waiting_for_greeting, F.text)
async def mirror_greeting_process(message: Message, state: FSMContext, db: Database):
    """Сохранить приветствие"""
    data = await state.get_data()
    mirror_id = data["target_mirror_id"]
    
    greeting_text = message.text.strip()
    if not greeting_text:
        await message.answer("❌ Сообщение не может быть пустым.")
        return

    await db.update_mirror_settings(mirror_id, greeting_text=greeting_text)
    await state.clear()
    
    await message.answer("✅ Приветствие успешно обновлено!")


# ===== НАЦЕНКА =====

@router.callback_query(F.data.startswith("mirror_markup_"))
async def mirror_markup_start(call: CallbackQuery, state: FSMContext, db: Database):
    """Начать изменение наценки"""
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("❌ Доступ запрещен!", show_alert=True)
        return

    await state.set_state(MirrorAdminState.waiting_for_markup)
    await state.update_data(target_mirror_id=mirror_id)
    
    text = (
        "💵 **Установка наценки**\n\n"
        f"Текущая наценка: {mirror['markup_percent']}%\n\n"
        "Введите процент наценки (0-100):\n"
        "• Пример: 50 (это означает наценка 50%)\n"
        "• Все цены товаров будут увеличены на указанный процент"
    )
    
    await call.message.answer(text)
    await call.answer()


@router.message(MirrorAdminState.waiting_for_markup, F.text)
async def mirror_markup_process(message: Message, state: FSMContext, db: Database):
    """Сохранить наценку"""
    data = await state.get_data()
    mirror_id = data["target_mirror_id"]
    
    try:
        markup_percent = int(message.text.strip())
        if not 0 <= markup_percent <= 100:
            await message.answer("❌ Процент должен быть между 0 и 100.")
            return
    except ValueError:
        await message.answer("❌ Введите число.")
        return

    await db.update_mirror_settings(mirror_id, markup_percent=markup_percent)
    await state.clear()
    
    await message.answer(f"✅ Наценка успешно установлена на {markup_percent}%")


# ===== КАНАЛ ПОДПИСКИ =====

@router.callback_query(F.data.startswith("mirror_channel_"))
async def mirror_channel_menu(call: CallbackQuery, db: Database):
    """Меню управления подпиской на канал"""
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("❌ Доступ запрещен!", show_alert=True)
        return

    text = (
        "📢 **Управление подпиской на канал**\n\n"
        "Вы можете настроить обязательную подписку на ваш канал для новых пользователей.\n"
        "После настройки пользователи должны будут подписаться перед использованием бота.\n\n"
    )
    
    if mirror.get("channel_link"):
        text += f"✅ Текущий канал: @{mirror.get('channel_username')}\n"
        text += f"   Ссылка: {mirror.get('channel_link')}\n\n"
    else:
        text += "❌ Канал не настроен\n\n"

    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить/изменить канал", callback_data=f"mirror_add_channel_{mirror_id}")],
    ]
    
    if mirror.get("channel_link"):
        keyboard.append([InlineKeyboardButton(text="🗑️ Удалить подписку", callback_data=f"mirror_remove_channel_{mirror_id}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"mirror_settings_{mirror_id}")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await call.answer()


@router.callback_query(F.data.startswith("mirror_add_channel_"))
async def mirror_add_channel_start(call: CallbackQuery, state: FSMContext):
    """Начать добавление канала"""
    mirror_id = int(call.data.split("_")[3])
    await state.set_state(MirrorAdminState.waiting_for_channel_link)
    await state.update_data(target_mirror_id=mirror_id)
    
    await call.message.answer(
        "🔗 **Введите ссылку на ваш канал**\n\n"
        "Пример: https://t.me/mychannel"
    )
    await call.answer()


@router.message(MirrorAdminState.waiting_for_channel_link, F.text)
async def mirror_channel_link_process(message: Message, state: FSMContext):
    """Обработка ссылки на канал"""
    channel_link = message.text.strip()
    
    if not channel_link.startswith(("https://t.me/", "https://telegram.me/", "t.me/")):
        await message.answer("❌ Неверный формат ссылки. Используйте формат: https://t.me/mychannel")
        return
    
    # Извлекаем username из ссылки
    if channel_link.startswith("https://t.me/"):
        channel_username = channel_link.replace("https://t.me/", "").split("?")[0].strip()
    elif channel_link.startswith("https://telegram.me/"):
        channel_username = channel_link.replace("https://telegram.me/", "").split("?")[0].strip()
    elif channel_link.startswith("t.me/"):
        channel_username = channel_link.replace("t.me/", "").split("?")[0].strip()
    else:
        channel_username = ""
    
    if not channel_username or "/" in channel_username:
        await message.answer("❌ Неверный username канала. Пожалуйста, укажите корректную ссылку на Telegram канал.")
        return
    
    await state.update_data(channel_link=channel_link, channel_username=channel_username)
    await state.set_state(MirrorAdminState.waiting_for_channel_username)
    
    await message.answer(
        f"✅ Ссылка: {channel_link}\n"
        f"Username: @{channel_username}\n\n"
        f"Это корректно? Если да, напишите: подтвердить, если нет, напишите: отмена"
    )


@router.message(MirrorAdminState.waiting_for_channel_username, F.text)
async def mirror_channel_confirm(message: Message, state: FSMContext, db: Database):
    """Подтверждение канала"""
    if message.text.lower() == "подтвердить":
        data = await state.get_data()
        mirror_id = data["target_mirror_id"]
        channel_link = data["channel_link"]
        channel_username = data["channel_username"]
        
        await db.update_mirror_settings(mirror_id, channel_link=channel_link, channel_username=channel_username)
        await state.clear()
        
        await message.answer(
            f"✅ **Канал успешно добавлен!**\n\n"
            f"Новые пользователи будут должны подписаться на @{channel_username} перед использованием бота."
        )
        
    elif message.text.lower() == "отмена":
        await state.clear()
        await message.answer("❌ Отменено.")
    else:
        await message.answer("❌ Пожалуйста, напишите: подтвердить или отмена")


@router.callback_query(F.data.startswith("mirror_remove_channel_"))
async def mirror_remove_channel(call: CallbackQuery, db: Database):
    """Удалить подписку на канал"""
    mirror_id = int(call.data.split("_")[3])
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    await db.update_mirror_settings(mirror_id, channel_link=None, channel_username=None)
    
    await call.message.answer("✅ Подписка на канал удалена!")
    await call.answer()


# ===== РАССЫЛКА =====

@router.callback_query(F.data.startswith("mirror_mailing_"))
async def mirror_mailing_start(call: CallbackQuery, state: FSMContext, db: Database):
    """Начать рассылку"""
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    users = await db.get_mirror_users(mirror_id)
    
    if not users:
        await call.answer("❌ В этом зеркале нет пользователей!", show_alert=True)
        return
    
    await state.set_state(MirrorAdminState.waiting_for_broadcast_text)
    await state.update_data(target_mirror_id=mirror_id)
    
    text = (
        f"📢 **Рассылка в зеркало @{mirror['bot_username']}**\n\n"
        f"Пользователей для отправки: {len(users)}\n\n"
        f"Напишите текст рассылки (поддерживается Markdown):\n"
        f"• *жирный текст*\n"
        f"• [ссылка](url)\n"
        f"• код"
    )
    
    await call.message.answer(text)
    await call.answer()


@router.message(MirrorAdminState.waiting_for_broadcast_text, F.text)
async def mirror_broadcast_text(message: Message, state: FSMContext, db: Database):
    """Получить текст рассылки"""
    data = await state.get_data()
    mirror_id = data["target_mirror_id"]
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror or mirror["owner_id"] != message.from_user.id:
        await message.answer("❌ Доступ запрещен!")
        await state.clear()
        return
    
    broadcast_text = message.text.strip()
    if not broadcast_text:
        await message.answer("❌ Текст не может быть пустым.")
        return
    
    users = await db.get_mirror_users(mirror_id)
    if not users:
        await message.answer("❌ В этом зеркале нет пользователей.")
        await state.clear()
        return
    
    # Подтверждение
    await message.answer(
        f"📊 **Подтверждение рассылки**\n\n"
        f"Получателей: **{len(users)}**\n"
        f"Зеркало: @{mirror['bot_username']}\n\n"
        f"**Текст рассылки:**\n{broadcast_text}\n\n"
        f"Подтвердите отправку, напишите: отправить или отмена"
    )
    
    await state.update_data(broadcast_text=broadcast_text, user_ids=users)
    await state.set_state(MirrorAdminState.waiting_for_broadcast_confirm)


@router.message(MirrorAdminState.waiting_for_broadcast_confirm, F.text)
async def mirror_broadcast_confirm(message: Message, state: FSMContext, db: Database, bot: Bot):
    """Подтвердить рассылку"""
    if message.text.lower() == "отправить":
        data = await state.get_data()
        broadcast_text = data["broadcast_text"]
        user_ids = data["user_ids"]
        mirror_id = data["target_mirror_id"]
        
        mirror = await db.get_mirror_by_id(mirror_id)
        if not mirror:
            await message.answer("❌ Зеркало не найдено.")
            await state.clear()
            return
        
        # Отправляем рассылку
        sent_count = 0
        failed_count = 0
        
        for user_id in user_ids:
            try:
                # Отправляем от основного бота, не от зеркала
                await bot.send_message(
                    user_id,
                    broadcast_text,
                    parse_mode="Markdown"
                )
                sent_count += 1
            except Exception:
                failed_count += 1
        
        await state.clear()
        await message.answer(
            f"✅ **Рассылка завершена!**\n\n"
            f"✅ Успешно отправлено: **{sent_count}**\n"
            f"❌ Ошибок: **{failed_count}**\n\n"
            f"Всего пользователей: **{len(user_ids)}**"
        )
        
    elif message.text.lower() == "отмена":
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
    else:
        await message.answer("❌ Пожалуйста, напишите: отправить или отмена")
