from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db import Database

router = Router()


class MirrorAdminState(StatesGroup):
    waiting_for_token = State()
    waiting_for_markup = State()
    waiting_for_greeting = State()
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_withdraw_req = State()
    waiting_for_channel_link = State()
    waiting_for_channel_username = State()


# Панель управления зеркалами для партнера
@router.callback_query(F.data == "my_mirrors_btn")
async def mirror_partner_menu_cb(call: CallbackQuery, db: Database):
    await mirror_partner_menu(call.message, db)
    await call.answer()


@router.message(F.text == "🪞 Мои Зеркала")
async def mirror_partner_menu(message: Message, db: Database):
    mirrors = await db.get_mirrors_by_owner(message.from_user.id)
    if not mirrors:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Подключить новое Зеркало", callback_data="add_new_mirror")]
        ])
        await message.answer(
            "🪞 **Система Зеркал (Партнерская программа)**\n\n"
            "У вас пока нет подключенных ботов-зеркал.\n"
            "Вы можете подключить своего бота через Token от @BotFather, настроить собственную наценку (маржу) и получать прибыль с каждой продажи!",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return

    text = "🪞 **Ваши подключенные Зеркала:**\n\n"
    keyboard = []
    for m in mirrors:
        text += f"🤖 @{m['bot_username']} | Наценка: {m['markup_percent']}% | Баланс: {m['balance']} ₽\n"
        keyboard.append([InlineKeyboardButton(text=f"⚙️ Управление @{m['bot_username']}", callback_data=f"manage_mirror_{m['id']}")])
    
    keyboard.append([InlineKeyboardButton(text="➕ Подключить еще Зеркало", callback_data="add_new_mirror")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")


@router.callback_query(F.data == "add_new_mirror")
async def start_add_mirror(call: CallbackQuery, state: FSMContext):
    await state.set_state(MirrorAdminState.waiting_for_token)
    await call.message.answer(
        "🔑 **Подключение нового Зеркала**\n\n"
        "1. Перейдите в @BotFather и создайте нового бота (/newbot).\n"
        "2. Скопируйте и отправьте сюда полученный API Token:\n"
        "(Пример: 1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ)"
    )


@router.message(MirrorAdminState.waiting_for_token)
async def process_mirror_token(message: Message, state: FSMContext, db: Database):
    token = message.text.strip()
    if ":" not in token or len(token) < 20:
        await message.answer("❌ Неверный формат токена Telegram бота. Попробуйте еще раз.")
        return
    
    from aiogram import Bot
    try:
        test_bot = Bot(token=token)
        me = await test_bot.get_me()
        await test_bot.session.close()
    except Exception as e:
        await message.answer("❌ Не удалось проверить токен бота. Убедитесь, что токен верен.")
        return

    existing = await db.get_mirror_by_token(token)
    if existing:
        await message.answer("❌ Этот бот уже зарегистрирован в системе!")
        await state.clear()
        return

    mirror_id = await db.create_mirror(bot_token=token, bot_username=me.username, owner_id=message.from_user.id)
    await state.clear()
    await message.answer(
        f"🎉 **Зеркало @{me.username} успешно добавлено в систему!**\n\n"
        f"⚠️ **Важно**: Чтобы зеркало заступило в работу и стало реагировать на сообщения, перезапустите скрипт бота.\n"
        f"После перезапуска зеркало станет доступно для задавания наценки, рассылок и вывода дохода от $5.",
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("manage_mirror_"))
async def manage_mirror_details(call: CallbackQuery, db: Database):
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("Доступ запрещен!", show_alert=True)
        return

    users_cnt = await db.get_mirror_users_count(mirror_id)
    text = (
        f"🤖 **Управление Зеркалом @{mirror['bot_username']}**\n\n"
        f"📈 Наценка: **{mirror['markup_percent']}%**\n"
        f"👥 Пользователей в зеркале: **{users_cnt}**\n"
        f"💰 Баланс вывода: **{mirror['balance']} ₽**\n\n"
        f"📢 Подписка на канал: {'✅ Настроена' if mirror.get('channel_link') else '❌ Не настроена'}\n"
        f"⚠️ *Обратите внимание: Техподдержка, каталоги едины для всех зеркал.*"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить наценку (%)", callback_data=f"set_markup_{mirror_id}")],
        [InlineKeyboardButton(text="📢 Подписка на канал", callback_data=f"setup_channel_{mirror_id}")],
        [InlineKeyboardButton(text="📣 Рассылка по своим пользователям", callback_data=f"broadcast_mirror_{mirror_id}")],
        [InlineKeyboardButton(text="💸 Запросить вывод средств (Мин. 500 ₽)", callback_data=f"withdraw_mirror_{mirror_id}")],
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_mirrors")]
    ])
    await call.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")


@router.callback_query(F.data == "back_to_mirrors")
async def back_to_mirrors_handler(call: CallbackQuery, db: Database):
    await call.message.delete()
    await mirror_partner_menu(call.message, db)


@router.callback_query(F.data.startswith("set_markup_"))
async def start_set_markup(call: CallbackQuery, state: FSMContext):
    mirror_id = int(call.data.split("_")[2])
    await state.update_data(target_mirror_id=mirror_id)
    await state.set_state(MirrorAdminState.waiting_for_markup)
    await call.message.answer("📈 Введите желаемый процент наценки к базовой цене товара (например: 10 или 25):")


@router.message(MirrorAdminState.waiting_for_markup)
async def process_set_markup(message: Message, state: FSMContext, db: Database):
    if not message.text.isdigit() or int(message.text) < 0 or int(message.text) > 300:
        await message.answer("❌ Введите число от 0 до 300.")
        return
    
    data = await state.get_data()
    mirror_id = data["target_mirror_id"]
    markup_val = int(message.text)
    await db.update_mirror_settings(mirror_id, markup_percent=markup_val)
    await state.clear()
    await message.answer(f"✅ Наценка успешно изменена на **{markup_val}%**!", parse_mode="Markdown")


@router.callback_query(F.data.startswith("withdraw_mirror_"))
async def start_withdraw_request(call: CallbackQuery, state: FSMContext, db: Database):
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    if not mirror or mirror["balance"] < 500: # 500 рублей ≈ $5
        await call.answer("❌ Минимальная сумма вывода 500 ₽ ($5). Накопите достаточный баланс!", show_alert=True)
        return

    await state.update_data(target_mirror_id=mirror_id, withdraw_amount=mirror["balance"])
    await state.set_state(MirrorAdminState.waiting_for_withdraw_req)
    await call.message.answer(
        f"💸 **Вывод средств ($5+)**\n\n"
        f"Доступная сумма: **{mirror['balance']} ₽**\n"
        f"Введите реквизиты для получения средств (например, USDT TRC20, TON кошелек или юзернейм CryptoBot):",
        parse_mode="Markdown"
    )


@router.message(MirrorAdminState.waiting_for_withdraw_req)
async def process_withdraw_request(message: Message, state: FSMContext, db: Database, config, bot):
    data = await state.get_data()
    mirror_id = data["target_mirror_id"]
    amount = data["withdraw_amount"]
    requisites = message.text.strip()

    try:
        req_id = await db.create_withdrawal_request(mirror_id, message.from_user.id, amount, requisites)
        await state.clear()
        await message.answer("✅ **Заявка на вывод отправлена администратору!** Ожидайте выплаты.", parse_mode="Markdown")
        
        # Уведомление мейн-админа
        if config.admin_group_id:
            mirror = await db.get_mirror_by_id(mirror_id)
            await bot.send_message(
                config.admin_group_id,
                f"📥 **Новая заявка на вывод с Зеркала @{mirror['bot_username']}!**\n\n"
                f"ID заявки: #{req_id}\n"
                f"Владелец: TG ID {message.from_user.id}\n"
                f"Сумма: **{amount} ₽**\n"
                f"Реквизиты: {requisites}",
                parse_mode="Markdown"
            )
    except Exception as e:
        await state.clear()
        await message.answer(f"❌ Ошибка вывода: {e}")


@router.callback_query(F.data.startswith("setup_channel_"))
async def setup_channel_start(call: CallbackQuery, state: FSMContext, db: Database):
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("Доступ запрещен!", show_alert=True)
        return
    
    current_link = mirror.get("channel_link")
    text = (
        "📢 **Управление подпиской на канал**\n\n"
        "Вы можете настроить обязательную подписку на ваш канал для новых пользователей.\n"
        "После настройки пользователи должны будут подписаться перед использованием бота.\n\n"
    )
    if current_link:
        text += f"Текущая ссылка: {current_link}\n\n"
    
    text += (
        "Выберите действие:"
    )
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить/изменить канал", callback_data=f"add_channel_{mirror_id}")],
    ])
    
    if current_link:
        markup.inline_keyboard.append(
            [InlineKeyboardButton(text="🗑️ Удалить подписку", callback_data=f"remove_channel_{mirror_id}")]
        )
    
    markup.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_mirror_{mirror_id}")])
    
    await call.message.answer(text, reply_markup=markup, parse_mode="Markdown")
    await call.answer()


@router.callback_query(F.data.startswith("add_channel_"))
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    mirror_id = int(call.data.split("_")[2])
    await state.update_data(target_mirror_id=mirror_id)
    await state.set_state(MirrorAdminState.waiting_for_channel_link)
    await call.message.answer(
        "🔗 **Введите ссылку на ваш канал**\n\n"
        "Пример: https://t.me/mychannel"
    )
    await call.answer()


@router.message(MirrorAdminState.waiting_for_channel_link, F.text)
async def process_channel_link(message: Message, state: FSMContext):
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
        await message.answer("❌ Неверный username канала. Пожалуйста, укажите корректную ссылку на Telegram канал.", parse_mode="Markdown")
        return
    
    await state.update_data(channel_link=channel_link, channel_username=channel_username)
    await state.set_state(MirrorAdminState.waiting_for_channel_username)
    await message.answer(
        f"✅ Ссылка: {channel_link}\n"
        f"Username: @{channel_username}\n\n"
        f"Это корректно? Если да, напишите: подтвердить, если нет, напишите: отмена"
    )


@router.message(MirrorAdminState.waiting_for_channel_username, F.text)
async def confirm_channel(message: Message, state: FSMContext, db: Database):
    if message.text.lower() == "подтвердить":
        data = await state.get_data()
        mirror_id = data["target_mirror_id"]
        channel_link = data["channel_link"]
        channel_username = data["channel_username"]
        
        await db.update_mirror_settings(mirror_id, channel_link=channel_link, channel_username=channel_username)
        await state.clear()
        await message.answer(
            f"✅ **Канал успешно добавлен!**\n\n"
            f"Новые пользователи будут должны подписаться на @{channel_username} перед использованием бота.",
            parse_mode="Markdown"
        )
    elif message.text.lower() == "отмена":
        await state.clear()
        await message.answer("❌ Отменено.")
    else:
        await message.answer("❌ Пожалуйста, напишите: подтвердить или отмена")


@router.callback_query(F.data.startswith("remove_channel_"))
async def remove_channel(call: CallbackQuery, db: Database):
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("Доступ запрещен!", show_alert=True)
        return
    
    await db.update_mirror_settings(mirror_id, channel_link=None, channel_username=None)
    await call.answer("✅ Подписка на канал удалена!", show_alert=False)
    
    # Возвращаемся в меню управления каналом
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data=f"add_channel_{mirror_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"manage_mirror_{mirror_id}")]
    ])
    await call.message.edit_text(
        "📢 **Управление подпиской на канал**\n\n"
        "Канал удален. Вы можете добавить новый канал.",
        reply_markup=markup,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("broadcast_mirror_"))
async def start_broadcast_mirror(call: CallbackQuery, state: FSMContext, db: Database):
    mirror_id = int(call.data.split("_")[2])
    mirror = await db.get_mirror_by_id(mirror_id)
    if not mirror or mirror["owner_id"] != call.from_user.id:
        await call.answer("Доступ запрещен!", show_alert=True)
        return
    
    users_count = await db.get_mirror_users_count(mirror_id)
    
    await state.update_data(target_mirror_id=mirror_id)
    await state.set_state(MirrorAdminState.waiting_for_broadcast_text)
    await call.message.answer(
        f"📣 **Рассылка для зеркала @{mirror['bot_username']}**\n\n"
        f"Пользователей в зеркале: **{users_count}**\n\n"
        f"Напишите текст рассылки (поддерживается Markdown):\n"
        f"• *жирный текст*\n"
        f"• [ссылка](url)\n"
        f"• код",
        parse_mode="Markdown"
    )
    await call.answer()


@router.message(MirrorAdminState.waiting_for_broadcast_text, F.text)
async def process_broadcast_mirror(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    mirror_id = data["target_mirror_id"]
    mirror = await db.get_mirror_by_id(mirror_id)
    
    if not mirror:
        await message.answer("❌ Зеркало не найдено.")
        await state.clear()
        return
    
    broadcast_text = message.text.strip()
    if not broadcast_text:
        await message.answer("❌ Текст не может быть пустым.")
        return
    
    # Получаем всех пользователей зеркала
    users = await db.get_mirror_users(mirror_id)
    
    if not users:
        await message.answer("❌ В этом зеркале нет пользователей.")
        await state.clear()
        return
    
    # Подтверждение перед отправкой
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
async def confirm_broadcast_mirror(message: Message, state: FSMContext, db: Database, bot: Bot):
    if message.text.lower() == "отправить":
        data = await state.get_data()
        mirror_id = data.get("target_mirror_id")
        broadcast_text = data.get("broadcast_text")
        users = data.get("user_ids", [])
        
        if not mirror_id or not broadcast_text or not users:
            await message.answer("❌ Ошибка данных рассылки.")
            await state.clear()
            return
        
        mirror = await db.get_mirror_by_id(mirror_id)
        if not mirror:
            await message.answer("❌ Зеркало не найдено.")
            await state.clear()
            return
        
        mirror_bot = Bot(token=mirror["bot_token"])
        sent_count = 0
        failed_count = 0
        
        await message.answer("🚀 Начинаю отправку рассылки...")
        
        # Отправляем рассылку всем пользователям
        for user_id in users:
            try:
                await mirror_bot.send_message(
                    user_id,
                    broadcast_text,
                    parse_mode="Markdown"
                )
                sent_count += 1
            except Exception:
                failed_count += 1
        
        await mirror_bot.session.close()
        
        await state.clear()
        await message.answer(
            f"✅ **Рассылка завершена!**\n\n"
            f"✅ Успешно отправлено: **{sent_count}**\n"
            f"❌ Ошибок: **{failed_count}**\n\n"
            f"Всего пользователей: **{len(users)}**",
            parse_mode="Markdown"
        )
        
    elif message.text.lower() == "отмена":
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
    else:
        await message.answer("❌ Пожалуйста, напишите: отправить или отмена")

