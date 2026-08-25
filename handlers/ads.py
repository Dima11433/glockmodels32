import datetime
import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from db import Database
from payments import Payments
import texts

router = Router()

# Цены по умолчанию (будут динамически настраиваться через БД или конфиг)
# Для бота 1 (GLOCKSHOP23 / glsx_shop_bot)
DEFAULT_PRICES_SHOP1 = {
    "mail_no_btn": {"13:00": 1500, "16:00": 2000, "19:00": 3000},  # в центах ($15, $20, $30)
    "mail_with_btn": {"13:00": 2000, "16:00": 3000, "19:00": 4000},  # ($20, $30, $40)
    "button_days": {1: 1400, 3: 2000, 7: 3000},  # ($14, $20, $30)
    "welcome_days": {1: 1500, 3: 2000},  # ($15, $20)
    "manager": "glock_support",
    "base_text": "7000+ чел."
}


class AdMailingFSM(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    choosing_btn_option = State()
    entering_text = State()
    entering_btn_data = State()
    confirm_payment = State()


class AdButtonFSM(StatesGroup):
    choosing_days = State()
    entering_title = State()
    entering_url = State()
    confirm_payment = State()


class AdWelcomeFSM(StatesGroup):
    choosing_days = State()
    entering_text = State()
    confirm_payment = State()


async def get_ad_config(db: Database) -> dict:
    """Загружает настройки рекламы из БД или возвращает дефолтные."""
    m = await db.get_setting("ads:manager") or "glock_support"
    b = await db.get_setting("ads:base_text") or "7000+ чел."
    return {
        "mail_no_btn": {"13:00": 1500, "16:00": 2000, "19:00": 3000},
        "mail_with_btn": {"13:00": 2000, "16:00": 3000, "19:00": 4000},
        "button_days": {1: 1400, 3: 2000, 7: 3000},
        "welcome_days": {1: 1500, 3: 2000},
        "manager": m,
        "base_text": b
    }


# ═══════════════════════════════════════════════════════════════════════════
# 🌴 ГЛАВНОЕ МЕНЮ РАЗДЕЛА «РЕКЛАМА»
# ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "menu:ads")
async def menu_ads(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    cfg = await get_ad_config(db)
    
    # Получаем активные рекламные кнопки
    buttons = await db.get_active_ad_buttons()
    
    text = (
        "🌴 <b>РЕКЛАМА И СОТРУДНИЧЕСТВО</b>\n\n"
        f"👥 <b>Активная база пользователей:</b> <code>{cfg['base_text']}</code>\n\n"
        "Здесь вы можете заказать продвижение вашего проекта:\n"
        "• 📨 <b>Разовая рассылка</b> на всю базу по времени\n"
        "• 🔘 <b>Аренда рекламной кнопки</b> в этом разделе\n"
        "• 👋 <b>Реклама в приветствии</b> (/start) для новых пользователей\n\n"
        f"📲 <b>По всем вопросам и брони:</b> @{cfg['manager'].lstrip('@')}"
    )

    rows = []
    # Если есть активные спонсорские кнопки - отображаем их вверху
    if buttons:
        rows.append([InlineKeyboardButton(text="⭐ НАШИ СПОНСОРЫ ⭐", callback_data="noop")])
        for b in buttons:
            title = b["button_title"] or "Спонсор"
            url = b["button_url"] or f"https://t.me/{cfg['manager']}"
            rows.append([InlineKeyboardButton(text=f"🔘 {title}", url=url)])
        rows.append([InlineKeyboardButton(text="━━━━━━━━━━━━━━━━", callback_data="noop")])

    # Кнопки для заказа
    rows.append([InlineKeyboardButton(text="📨 Заказать рассылку", callback_data="ads:order_mail")])
    rows.append([InlineKeyboardButton(text="🔘 Арендовать рекламную кнопку", callback_data="ads:order_btn")])
    rows.append([InlineKeyboardButton(text="👋 Реклама в приветствии (/start)", callback_data="ads:order_welc")])
    rows.append([InlineKeyboardButton(text="💬 Менеджер по рекламе", url=f"https://t.me/{cfg['manager'].lstrip('@')}")])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:main")])

    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════════════
# 📨 ЗАКАЗ РАССЫЛКИ (С БРОНИРОВАНИЕМ ВРЕМЕНИ)
# ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "ads:order_mail")
async def ads_order_mail_start(cb: CallbackQuery, state: FSMContext):
    today = datetime.date.today()
    d0 = today.strftime("%Y-%m-%d")
    d1 = (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    d2 = (today + datetime.timedelta(days=2)).strftime("%Y-%m-%d")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📅 Сегодня ({today.strftime('%d.%m')})", callback_data=f"ads:mdate:{d0}")],
        [InlineKeyboardButton(text=f"📅 Завтра ({(today + datetime.timedelta(days=1)).strftime('%d.%m')})", callback_data=f"ads:mdate:{d1}")],
        [InlineKeyboardButton(text=f"📅 Послезавтра ({(today + datetime.timedelta(days=2)).strftime('%d.%m')})", callback_data=f"ads:mdate:{d2}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await state.set_state(AdMailingFSM.choosing_date)
    await cb.message.answer("📅 <b>Шаг 1/4:</b> Выберите дату для проведения рассылки:", reply_markup=markup, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("ads:mdate:"))
async def ads_order_mail_date_chosen(cb: CallbackQuery, db: Database, state: FSMContext):
    slot_date = cb.data.split(":")[2]
    await state.update_data(slot_date=slot_date)

    # Проверяем занятые слоты на эту дату
    booked_slots = await db.get_booked_mailing_slots(slot_date)
    times = ["13:00", "16:00", "19:00"]
    rows = []

    for t in times:
        if t in booked_slots:
            rows.append([InlineKeyboardButton(text=f"🔴 {t} — ⛔ ЗАНЯТО", callback_data="noop")])
        else:
            rows.append([InlineKeyboardButton(text=f"🟢 {t} — ✅ Свободно", callback_data=f"ads:mtime:{t}")])

    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)

    await state.set_state(AdMailingFSM.choosing_time)
    await cb.message.answer(
        f"⏰ <b>Шаг 2/4:</b> Выберите время рассылки на <b>{slot_date}</b>:\n"
        "<i>(Если время занято другим рекламодателем, его нельзя забронировать)</i>",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("ads:mtime:"))
async def ads_order_mail_time_chosen(cb: CallbackQuery, db: Database, state: FSMContext):
    slot_time = cb.data.split(":")[2]
    await state.update_data(slot_time=slot_time)

    cfg = await get_ad_config(db)
    p_no = cfg["mail_no_btn"].get(slot_time, 2000)
    p_with = cfg["mail_with_btn"].get(slot_time, 3000)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Без кнопки — {texts.fmt_usd(p_no)}", callback_data="ads:mopt:no_btn")],
        [InlineKeyboardButton(text=f"С кнопкой-ссылкой — {texts.fmt_usd(p_with)}", callback_data="ads:mopt:with_btn")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await state.set_state(AdMailingFSM.choosing_btn_option)
    await cb.message.answer(
        f"🔘 <b>Шаг 3/4:</b> Нужна ли кнопка со ссылкой внизу рекламного поста?\n\n"
        f"• Без кнопки: <b>{texts.fmt_usd(p_no)}</b>\n"
        f"• С кнопкой: <b>{texts.fmt_usd(p_with)}</b>",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("ads:mopt:"))
async def ads_order_mail_opt_chosen(cb: CallbackQuery, state: FSMContext):
    opt = cb.data.split(":")[2]
    has_button = (opt == "with_btn")
    await state.update_data(has_button=has_button)

    await state.set_state(AdMailingFSM.entering_text)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await cb.message.answer(
        "📝 <b>Шаг 4/4:</b> Отправьте рекламный пост (текст, фото или фото с описанием):\n\n"
        "<i>Поддерживается HTML-форматирование текста.</i>",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(AdMailingFSM.entering_text)
async def ads_order_mail_got_content(message: Message, state: FSMContext):
    text_content = message.caption or message.text or ""
    photo_file_id = message.photo[-1].file_id if message.photo else None

    if not text_content and not photo_file_id:
        return await message.answer("❌ Отправьте текст или фото для рассылки:")

    await state.update_data(text_content=text_content, photo_file_id=photo_file_id)
    data = await state.get_data()

    if data.get("has_button"):
        await state.set_state(AdMailingFSM.entering_btn_data)
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
        ])
        return await message.answer(
            "🔘 Введите данные для кнопки в формате:\n<code>Текст кнопки | https://t.me/ваша_ссылка</code>",
            reply_markup=markup,
            parse_mode="HTML"
        )

    await _show_mail_confirm(message, state)


@router.message(AdMailingFSM.entering_btn_data, F.text)
async def ads_order_mail_got_btn(message: Message, state: FSMContext):
    parts = message.text.split("|")
    if len(parts) < 2:
        return await message.answer(
            "❌ Неверный формат. Введите:\n<code>Текст кнопки | https://ссылка</code>",
            parse_mode="HTML"
        )
    btn_title = parts[0].strip()
    btn_url = parts[1].strip()

    if not btn_url.startswith("http://") and not btn_url.startswith("https://") and not btn_url.startswith("tg://"):
        return await message.answer("❌ Ссылка должна начинаться с https:// или tg://. Попробуйте ещё раз:")

    await state.update_data(btn_title=btn_title, btn_url=btn_url)
    await _show_mail_confirm(message, state)


async def _show_mail_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    cfg = await get_ad_config(message.bot["db"] if hasattr(message.bot, "__getitem__") else None)  # type: ignore
    
    slot_time = data["slot_time"]
    has_btn = data.get("has_button", False)
    price_cents = cfg["mail_with_btn"].get(slot_time, 3000) if has_btn else cfg["mail_no_btn"].get(slot_time, 2000)
    await state.update_data(price_cents=price_cents)

    text = (
        "🧾 <b>ПОДТВЕРЖДЕНИЕ БРОНИРОВАНИЯ РАССЫЛКИ</b>\n\n"
        f"📅 <b>Дата:</b> {data['slot_date']}\n"
        f"⏰ <b>Время:</b> {data['slot_time']}\n"
        f"🔘 <b>Кнопка:</b> {'Да' if has_btn else 'Нет'}\n"
        f"💵 <b>Стоимость:</b> {texts.fmt_usd(price_cents)}\n\n"
        "Выберите способ оплаты:"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💰 Оплатить {texts.fmt_usd(price_cents)} с баланса", callback_data="ads:pay_mail:balance")],
        [InlineKeyboardButton(text=f"🤖 CryptoBot — {texts.fmt_usd(price_cents)}", callback_data="ads:pay_mail:cryptopay")],
        [InlineKeyboardButton(text=f"🚀 xRocket — {texts.fmt_usd(price_cents)}", callback_data="ads:pay_mail:xrocket")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await state.set_state(AdMailingFSM.confirm_payment)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("ads:pay_mail:"))
async def ads_pay_mail(cb: CallbackQuery, db: Database, payments: Payments, state: FSMContext):
    method = cb.data.split(":")[2]
    data = await state.get_data()
    price_cents = data.get("price_cents", 2000)

    user = await db.get_user(cb.from_user.id)
    if not user:
        return await cb.answer("Ошибка пользователя")

    if method == "balance":
        if user["balance"] < price_cents:
            return await cb.answer("Недостаточно средств на балансе! Пополните баланс в профиле.", show_alert=True)
        
        # Списываем баланс
        await db.update_balance(cb.from_user.id, -price_cents)
        slot_id = await db.add_ad_slot(
            ad_type="mailing",
            user_id=cb.from_user.id,
            username=cb.from_user.username,
            text_content=data.get("text_content", ""),
            price_cents=price_cents,
            slot_date=data.get("slot_date"),
            slot_time=data.get("slot_time"),
            has_button=data.get("has_button", False),
            photo_file_id=data.get("photo_file_id"),
            button_title=data.get("btn_title"),
            button_url=data.get("btn_url"),
            status="active"
        )
        await state.clear()
        await cb.message.answer(
            f"🎉 <b>Рассылка успешно забронирована и оплачена!</b>\n\n"
            f"📅 <b>Дата:</b> {data['slot_date']}\n"
            f"⏰ <b>Время:</b> {data['slot_time']}\n"
            f"Бот автоматически отправит ваш пост всем пользователям в назначенное время.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌴 В раздел Реклама", callback_data="menu:ads")]]),
            parse_mode="HTML"
        )
        await cb.answer()
        return

    # Оплата через крипту
    try:
        invoice_id, pay_url = await payments.create_invoice(price_cents, f"Рассылка {data['slot_date']} {data['slot_time']}", provider=method)
    except Exception as e:
        return await cb.answer(f"Ошибка создания счёта: {e}", show_alert=True)

    await db.create_invoice(invoice_id, cb.from_user.id, "ads_mailing", price_cents, pay_url, provider=method)
    # Сохраняем слот в ожидании
    slot_id = await db.add_ad_slot(
        ad_type="mailing",
        user_id=cb.from_user.id,
        username=cb.from_user.username,
        text_content=data.get("text_content", ""),
        price_cents=price_cents,
        slot_date=data.get("slot_date"),
        slot_time=data.get("slot_time"),
        has_button=data.get("has_button", False),
        photo_file_id=data.get("photo_file_id"),
        button_title=data.get("btn_title"),
        button_url=data.get("btn_url"),
        status="pending"
    )
    await state.clear()

    prov_name = "xRocket" if method == "xrocket" else "CryptoBot"
    msg_text = (
        f"🧾 <b>Счёт на бронирование рассылки ({prov_name}) создан</b>\n\n"
        f"💵 Сумма: {texts.fmt_usd(price_cents)}\n"
        "💡 <i>Оплатите счёт по ссылке ниже. После оплаты слот будет моментально забронирован!</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить счёт", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"checkinv:{invoice_id}")],
        [InlineKeyboardButton(text="🌴 В меню рекламы", callback_data="menu:ads")]
    ])
    await cb.message.answer(msg_text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════════════
# 🔘 АРЕНДА КНОПКИ В РАЗДЕЛЕ РЕКЛАМЫ
# ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "ads:order_btn")
async def ads_order_btn_start(cb: CallbackQuery, db: Database, state: FSMContext):
    cfg = await get_ad_config(db)
    prices = cfg["button_days"]

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"24 часа (1 день) — {texts.fmt_usd(prices[1])}", callback_data="ads:btndays:1")],
        [InlineKeyboardButton(text=f"3 дня — {texts.fmt_usd(prices[3])}", callback_data="ads:btndays:3")],
        [InlineKeyboardButton(text=f"7 дней (неделя) — {texts.fmt_usd(prices[7])}", callback_data="ads:btndays:7")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await state.set_state(AdButtonFSM.choosing_days)
    await cb.message.answer("🔘 <b>Шаг 1/3:</b> Выберите срок аренды рекламной кнопки:", reply_markup=markup, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("ads:btndays:"))
async def ads_order_btn_days_chosen(cb: CallbackQuery, db: Database, state: FSMContext):
    days = int(cb.data.split(":")[2])
    cfg = await get_ad_config(db)
    price_cents = cfg["button_days"].get(days, 2000)

    await state.update_data(days=days, price_cents=price_cents)
    await state.set_state(AdButtonFSM.entering_title)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await cb.message.answer(
        f"✏️ <b>Шаг 2/3:</b> Введите название для вашей кнопки (до 30 символов):\n"
        "<i>Например: 🔥 Скидки 50% в Glock Shop</i>",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(AdButtonFSM.entering_title, F.text)
async def ads_order_btn_title_entered(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) > 40:
        return await message.answer("❌ Название слишком длинное (макс. 40 символов). Введите короче:")

    await state.update_data(button_title=title)
    await state.set_state(AdButtonFSM.entering_url)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await message.answer(
        "🔗 <b>Шаг 3/3:</b> Отправьте ссылку для перехода при клике на кнопку:\n"
        "<i>Например: https://t.me/my_channel</i>",
        reply_markup=markup,
        parse_mode="HTML"
    )


@router.message(AdButtonFSM.entering_url, F.text)
async def ads_order_btn_url_entered(message: Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("tg://"):
        return await message.answer("❌ Ссылка должна начинаться с https:// или tg://. Попробуйте ещё раз:")

    await state.update_data(button_url=url)
    data = await state.get_data()
    price_cents = data["price_cents"]
    days = data["days"]
    title = data["button_title"]

    text = (
        "🧾 <b>ПОДТВЕРЖДЕНИЕ АРЕНДЫ КНОПКИ</b>\n\n"
        f"🔘 <b>Название:</b> {title}\n"
        f"🔗 <b>Ссылка:</b> {url}\n"
        f"⏳ <b>Срок аренды:</b> {days} дн.\n"
        f"💵 <b>Стоимость:</b> {texts.fmt_usd(price_cents)}\n\n"
        "Выберите способ оплаты:"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💰 Оплатить {texts.fmt_usd(price_cents)} с баланса", callback_data="ads:pay_btn:balance")],
        [InlineKeyboardButton(text=f"🤖 CryptoBot — {texts.fmt_usd(price_cents)}", callback_data="ads:pay_btn:cryptopay")],
        [InlineKeyboardButton(text=f"🚀 xRocket — {texts.fmt_usd(price_cents)}", callback_data="ads:pay_btn:xrocket")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await state.set_state(AdButtonFSM.confirm_payment)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("ads:pay_btn:"))
async def ads_pay_button(cb: CallbackQuery, db: Database, payments: Payments, state: FSMContext):
    method = cb.data.split(":")[2]
    data = await state.get_data()
    price_cents = data.get("price_cents", 2000)
    days = data.get("days", 1)

    user = await db.get_user(cb.from_user.id)
    if not user:
        return await cb.answer("Ошибка пользователя")

    expires_at = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    if method == "balance":
        if user["balance"] < price_cents:
            return await cb.answer("Недостаточно средств на балансе! Пополните баланс в профиле.", show_alert=True)
        
        await db.update_balance(cb.from_user.id, -price_cents)
        await db.add_ad_slot(
            ad_type="button",
            user_id=cb.from_user.id,
            username=cb.from_user.username,
            text_content="",
            price_cents=price_cents,
            days=days,
            button_title=data.get("button_title"),
            button_url=data.get("button_url"),
            status="active",
            expires_at=expires_at
        )
        await state.clear()
        await cb.message.answer(
            f"🎉 <b>Кнопка успешно арендована и добавлена в раздел Реклама!</b>\n\n"
            f"🔘 <b>Название:</b> {data.get('button_title')}\n"
            f"⏳ <b>Активна до:</b> {expires_at}\n\n"
            "Все пользователи бота уже видят вашу кнопку в меню!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌴 Посмотреть в меню рекламы", callback_data="menu:ads")]]),
            parse_mode="HTML"
        )
        await cb.answer()
        return

    # Crypto payment
    try:
        invoice_id, pay_url = await payments.create_invoice(price_cents, f"Аренда кнопки ({days} дн.)", provider=method)
    except Exception as e:
        return await cb.answer(f"Ошибка создания счёта: {e}", show_alert=True)

    await db.create_invoice(invoice_id, cb.from_user.id, "ads_button", price_cents, pay_url, provider=method)
    await state.clear()

    prov_name = "xRocket" if method == "xrocket" else "CryptoBot"
    msg_text = (
        f"🧾 <b>Счёт на аренду кнопки ({prov_name}) создан</b>\n\n"
        f"💵 Сумма: {texts.fmt_usd(price_cents)}\n"
        "💡 <i>После оплаты кнопка моментально активируется в разделе «Реклама»!</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить счёт", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"checkinv:{invoice_id}")],
        [InlineKeyboardButton(text="🌴 В меню рекламы", callback_data="menu:ads")]
    ])
    await cb.message.answer(msg_text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════════════
# 👋 РЕКЛАМА В ПРИВЕТСТВИИ (/START)
# ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "ads:order_welc")
async def ads_order_welc_start(cb: CallbackQuery, db: Database, state: FSMContext):
    cfg = await get_ad_config(db)
    prices = cfg["welcome_days"]

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"1 день — {texts.fmt_usd(prices[1])}", callback_data="ads:welcdays:1")],
        [InlineKeyboardButton(text=f"3 дня — {texts.fmt_usd(prices[3])}", callback_data="ads:welcdays:3")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await state.set_state(AdWelcomeFSM.choosing_days)
    await cb.message.answer("👋 <b>Шаг 1/2:</b> Выберите срок показа рекламы в приветствии (/start):", reply_markup=markup, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("ads:welcdays:"))
async def ads_order_welc_days_chosen(cb: CallbackQuery, db: Database, state: FSMContext):
    days = int(cb.data.split(":")[2])
    cfg = await get_ad_config(db)
    price_cents = cfg["welcome_days"].get(days, 3000)

    await state.update_data(days=days, price_cents=price_cents)
    await state.set_state(AdWelcomeFSM.entering_text)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await cb.message.answer(
        "📝 <b>Шаг 2/2:</b> Введите короткий текст рекламы со ссылкой (1-2 предложения):\n\n"
        "<i>Каждый новый пользователь, запустивший бота, увидит эту строчку в стартовом сообщении!</i>",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(AdWelcomeFSM.entering_text, F.text)
async def ads_order_welc_text_entered(message: Message, state: FSMContext):
    text_content = message.text.strip()
    await state.update_data(text_content=text_content)
    data = await state.get_data()
    price_cents = data["price_cents"]
    days = data["days"]

    text = (
        "🧾 <b>ПОДТВЕРЖДЕНИЕ РЕКЛАМЫ В ПРИВЕТСТВИИ</b>\n\n"
        f"📝 <b>Текст:</b> {text_content}\n"
        f"⏳ <b>Срок:</b> {days} дн.\n"
        f"💵 <b>Стоимость:</b> {texts.fmt_usd(price_cents)}\n\n"
        "Выберите способ оплаты:"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💰 Оплатить {texts.fmt_usd(price_cents)} с баланса", callback_data="ads:pay_welc:balance")],
        [InlineKeyboardButton(text=f"🤖 CryptoBot — {texts.fmt_usd(price_cents)}", callback_data="ads:pay_welc:cryptopay")],
        [InlineKeyboardButton(text=f"🚀 xRocket — {texts.fmt_usd(price_cents)}", callback_data="ads:pay_welc:xrocket")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:ads")]
    ])
    await state.set_state(AdWelcomeFSM.confirm_payment)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("ads:pay_welc:"))
async def ads_pay_welcome(cb: CallbackQuery, db: Database, payments: Payments, state: FSMContext):
    method = cb.data.split(":")[2]
    data = await state.get_data()
    price_cents = data.get("price_cents", 3000)
    days = data.get("days", 1)

    user = await db.get_user(cb.from_user.id)
    if not user:
        return await cb.answer("Ошибка пользователя")

    expires_at = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    if method == "balance":
        if user["balance"] < price_cents:
            return await cb.answer("Недостаточно средств на балансе! Пополните баланс в профиле.", show_alert=True)
        
        await db.update_balance(cb.from_user.id, -price_cents)
        await db.add_ad_slot(
            ad_type="welcome",
            user_id=cb.from_user.id,
            username=cb.from_user.username,
            text_content=data.get("text_content", ""),
            price_cents=price_cents,
            days=days,
            status="active",
            expires_at=expires_at
        )
        await state.clear()
        await cb.message.answer(
            f"🎉 <b>Реклама в приветствии успешно активирована!</b>\n\n"
            f"⏳ <b>Срок показа:</b> до {expires_at}\n\n"
            "Все новые пользователи бота будут видеть ваш текст при старте!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌴 В раздел Реклама", callback_data="menu:ads")]]),
            parse_mode="HTML"
        )
        await cb.answer()
        return

    # Crypto payment
    try:
        invoice_id, pay_url = await payments.create_invoice(price_cents, f"Реклама в приветствии ({days} дн.)", provider=method)
    except Exception as e:
        return await cb.answer(f"Ошибка создания счёта: {e}", show_alert=True)

    await db.create_invoice(invoice_id, cb.from_user.id, "ads_welcome", price_cents, pay_url, provider=method)
    await state.clear()

    prov_name = "xRocket" if method == "xrocket" else "CryptoBot"
    msg_text = (
        f"🧾 <b>Счёт на рекламу в приветствии ({prov_name}) создан</b>\n\n"
        f"💵 Сумма: {texts.fmt_usd(price_cents)}\n"
        "💡 <i>После оплаты реклама моментально появится в приветственном сообщении /start!</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить счёт", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"checkinv:{invoice_id}")],
        [InlineKeyboardButton(text="🌴 В меню рекламы", callback_data="menu:ads")]
    ])
    await cb.message.answer(msg_text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()
