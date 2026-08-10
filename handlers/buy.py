from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import texts
from db import Database
from payments import Payments, apply_paid_invoice

router = Router()


@router.callback_query(F.data.startswith("buynow:"))
async def buy_now(cb: CallbackQuery, db: Database, bot: Bot, config=None):
    product_id = int(cb.data.split(":")[1])
    result = await db.buy_with_balance(cb.from_user.id, product_id)
    if result.get("status") == "no_funds":
        return await cb.answer("Недостаточно средств на балансе", show_alert=True)
    if result.get("status") in ("gone", "out_of_stock"):
        return await cb.answer("Товар закончился или недоступен", show_alert=True)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    user = await db.get_user(cb.from_user.id)
    await deliver(bot, cb.from_user.id, result["name"], result.get("content_type"), result.get("content_value"))
    await notify_admin_sale(bot, db, cb.from_user.id, result["name"], result["price"], "balance", config)
    await db.add_log(cb.from_user.id, user['username'] if user else None, "купил_товар",
                    f"{result['name']} ({texts.fmt_usd(result['price'])})")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Написать отзыв", callback_data="write_review")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
    ])
    await cb.message.answer("✅ Покупка успешна! Спасибо за покупку! 🎉", reply_markup=markup)
    await cb.answer()


class TopupState(StatesGroup):
    amount = State()


async def deliver(bot: Bot, chat_id: int, name: str, content_type: str | None, content_value: str | None) -> None:
    caption = f"✅ Ваш товар: {name}"
    if content_type == "file":
        await bot.send_document(chat_id, content_value, caption=caption)
    else:
        await bot.send_message(chat_id, f"{caption}\n\n{content_value or ''}")


async def notify_admin_sale(bot: Bot, db: Database, user_id: int, name: str, price: int, method: str, config=None) -> None:
    """Уведомление в админ-канал о покупке с полной информацией включая реферала."""
    user = await db.get_user(user_id)
    if not user:
        return

    username = user["username"]
    user_link = f"tg://user?id={user_id}"
    user_mention = f'<a href="{user_link}">@{username}</a>' if username else f'<a href="{user_link}">#{user_id}</a>'

    method_name = {
        "balance": "💰 С баланса",
        "direct": "💳 CryptoBot",
        "free": "🎁 Бесплатно",
    }.get(method, method)

    # Проверяем реферала
    referrer_line = ""
    if user.get("referrer_id"):
        ref = await db.get_user(user["referrer_id"])
        if ref:
            ref_link = f"tg://user?id={ref['id']}"
            ref_mention = f'<a href="{ref_link}">@{ref["username"]}</a>' if ref["username"] else f'<a href="{ref_link}">#{ref["id"]}</a>'
            referrer_line = f"\n🤝 Пришёл по рефке: {ref_mention}"

    text = (
        f"🛒 <b>Новая покупка!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📦 Товар: <b>{name}</b>\n"
        f"💵 Сумма: <b>{texts.fmt_usd(price)}</b>\n"
        f"💳 Способ: {method_name}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Покупатель: {user_mention}\n"
        f"🆔 ID: <code>{user_id}</code>"
        f"{referrer_line}"
    )

    # Отправляем в группу логов (приоритет) и в личку админу
    sent = False
    if config and getattr(config, "admin_group_id", None):
        try:
            await bot.send_message(config.admin_group_id, text, parse_mode="HTML")
            sent = True
        except Exception:
            pass

    # Также пробуем отправить в личку через сохранённый admin_id
    admin_id = await db.get_setting("admin_id")
    if admin_id:
        try:
            await bot.send_message(int(admin_id), text, parse_mode="HTML")
        except Exception:
            pass



async def notify_payment_result(bot: Bot, db: Database, result: dict, config=None) -> None:
    user_id = result["user_id"]
    user = await db.get_user(user_id)
    try:
        if result["purpose"] == "topup":
            await bot.send_message(user_id, f"✅ Баланс пополнен на {texts.fmt_usd(result['amount'])}.")
            await db.add_log(user_id, user['username'] if user else None, "пополнил_баланс", 
                           f"{texts.fmt_usd(result['amount'])}")
        elif result.get("status") == "ok":
            await deliver(bot, user_id, result["name"], result["content_type"], result["content_value"])
            await notify_admin_sale(bot, db, user_id, result["name"], result["price"], "direct", config)
            
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Написать отзыв", callback_data="write_review")],
                [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
            ])
            await bot.send_message(user_id, f"✅ Спасибо за покупку! Товар успешно доставлен. 📦",
                                 reply_markup=markup)
            
            await db.add_log(user_id, user['username'] if user else None, "купил_товар", 
                           f"{result['name']} ({texts.fmt_usd(result['price'])})")
        elif result.get("status") == "refunded":
            await bot.send_message(
                user_id,
                "😔 Товар закончился, пока вы оплачивали счёт. "
                "Деньги зачислены на ваш баланс — приносим извинения.")
            await db.add_log(user_id, user['username'] if user else None, "возврат_средств", 
                           f"{texts.fmt_usd(result.get('amount', 0))}")
    except Exception:
        pass


def pay_kb(pay_url: str, invoice_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"checkinv:{invoice_id}")],
    ])


@router.callback_query(F.data.startswith("buy:"))
async def buy(cb: CallbackQuery, db: Database, payments: Payments):
    product_id = int(cb.data.split(":")[1])
    p = await db.get_product(product_id)
    if not p or not p["visible"]:
        return await cb.answer("Товар недоступен", show_alert=True)
    if p["kind"] == "oneoff" and await db.stock(product_id) == 0:
        return await cb.answer("Товара нет в наличии", show_alert=True)
    user = await db.get_user(cb.from_user.id)
    price = texts.fmt_usd(p["price"])
    if p["price"] == 0:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Получить бесплатно", callback_data=f"buyconfirm:{product_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"prod:{product_id}")],
        ])
        await cb.message.answer(f"«{p['name']}» — бесплатно. Подтвердите получение:", reply_markup=markup)
    elif user["balance"] >= p["price"]:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Оплатить {price} с баланса", callback_data=f"buyconfirm:{product_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"prod:{product_id}")],
        ])
        await cb.message.answer(f"Подтвердите покупку «{p['name']}» за {price}.", reply_markup=markup)
    else:
        rows = []
        if payments.enabled:
            rows.append([InlineKeyboardButton(text=f"💳 Оплатить {price} через CryptoBot",
                                              callback_data=f"paydirect:{product_id}")])
            rows.append([InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup")])
            note = ""
        else:
            note = f"\n\n{texts.PAYMENTS_DISABLED}"
        currency = user.get('currency', 'USD') if user else 'USD'
        await cb.message.answer(
            f"На балансе {texts.fmt_balance(user['balance'], currency)}, а товар стоит {price}.{note}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)
    await cb.answer()


@router.callback_query(F.data.startswith("buyconfirm:"))
async def buy_confirm(cb: CallbackQuery, db: Database, bot: Bot, config=None):
    product_id = int(cb.data.split(":")[1])
    result = await db.buy_with_balance(cb.from_user.id, product_id)
    if result["status"] == "no_funds":
        return await cb.answer("Недостаточно средств на балансе", show_alert=True)
    if result["status"] in ("gone", "out_of_stock"):
        return await cb.answer("Товар закончился или недоступен", show_alert=True)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    user = await db.get_user(cb.from_user.id)
    await deliver(bot, cb.from_user.id, result["name"], result["content_type"], result["content_value"])
    await notify_admin_sale(bot, db, cb.from_user.id, result["name"], result["price"], "balance", config)
    
    # Начисление маржи зеркалу, если бот запущен через зеркало
    token = bot.token if bot else None
    if token:
        mirror = await db.get_mirror_by_token(token)
        if mirror and mirror.get("markup_percent", 0) > 0:
            markup_percent = mirror["markup_percent"]
            base_price = result["price"]
            margin_amount = int(base_price * (markup_percent / 100))
            if margin_amount > 0:
                await db.add_mirror_balance(mirror["id"], margin_amount)

    # Логируем покупку
    await db.add_log(cb.from_user.id, user['username'] if user else None, "купил_товар",
                    f"{result['name']} ({texts.fmt_usd(result['price'])})")
    
    # Предлагаем написать отзыв
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Написать отзыв", callback_data="write_review")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
    ])
    await cb.message.answer("✅ Покупка успешна! Спасибо за покупку! 🎉",
                           reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data.startswith("paydirect:"))
async def pay_direct(cb: CallbackQuery, db: Database, payments: Payments):
    if not payments.enabled:
        return await cb.answer(texts.PAYMENTS_DISABLED, show_alert=True)
    product_id = int(cb.data.split(":")[1])
    p = await db.get_product(product_id)
    if not p or not p["visible"]:
        return await cb.answer("Товар недоступен", show_alert=True)
    if p["price"] == 0:
        return await cb.answer("Этот товар бесплатный — получите его через «Получить бесплатно»",
                               show_alert=True)
    item_id = None
    if p["kind"] == "oneoff":
        item_id = await db.reserve_item(product_id)
        if item_id is None:
            return await cb.answer("Товара нет в наличии", show_alert=True)
    try:
        invoice_id, pay_url = await payments.create_invoice(p["price"], f"Покупка: {p['name']}")
    except Exception:
        if item_id:
            await db.release_item(item_id)
        return await cb.answer("Не удалось создать счёт, попробуйте позже", show_alert=True)
    await db.create_invoice(invoice_id, cb.from_user.id, "purchase", p["price"], pay_url,
                            product_id=product_id, item_id=item_id)
    await cb.message.answer(
        f"🧾 Счёт на {texts.fmt_usd(p['price'])} создан.\n"
        "Оплатите в течение 30 минут — товар зарезервирован за вами. "
        "После оплаты нажмите «Проверить оплату».",
        reply_markup=pay_kb(pay_url, invoice_id))
    await cb.answer()


@router.callback_query(F.data.startswith("checkinv:"))
async def check_invoice(cb: CallbackQuery, db: Database, payments: Payments, bot: Bot, config=None):
    invoice_id = int(cb.data.split(":")[1])
    inv = await db.get_invoice(invoice_id)
    if not inv:
        return await cb.answer("Счёт не найден", show_alert=True)
    if inv["status"] == "paid":
        return await cb.answer("Этот счёт уже зачислен ✅", show_alert=True)
    if inv["status"] == "expired":
        return await cb.answer("Счёт истёк ❌", show_alert=True)
    if not payments.enabled:
        return await cb.answer(texts.PAYMENTS_DISABLED, show_alert=True)
    statuses = await payments.get_statuses([invoice_id])
    status = statuses.get(invoice_id)
    if status == "paid":
        result = await apply_paid_invoice(db, inv)
        if result:
            await notify_payment_result(bot, db, result, config)
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cb.answer("Оплата получена ✅")
    elif status == "expired":
        await db.mark_invoice_expired(invoice_id)
        if inv["item_id"]:
            await db.release_item(inv["item_id"])
        await cb.answer("Счёт истёк ❌", show_alert=True)
    else:
        await cb.answer("Оплата пока не поступила. Попробуйте через минуту.", show_alert=True)


@router.callback_query(F.data == "topup")
async def topup_start(cb: CallbackQuery, payments: Payments, state: FSMContext):
    if not payments.enabled:
        return await cb.answer(texts.PAYMENTS_DISABLED, show_alert=True)
    await state.set_state(TopupState.amount)
    await cb.message.answer("Введите сумму пополнения в долларах (например, 10 или 7.50):")
    await cb.answer()


@router.message(TopupState.amount, F.text)
async def topup_amount(message: Message, db: Database, payments: Payments, state: FSMContext):
    try:
        amount = round(float(message.text.replace(",", ".").replace("$", "").strip()), 2)
    except ValueError:
        return await message.answer("Не понял сумму. Введите число, например 10 или 7.50:")
    if not 1 <= amount <= 10000:
        return await message.answer("Сумма должна быть от $1 до $10000. Введите ещё раз:")
    cents = int(round(amount * 100))
    try:
        invoice_id, pay_url = await payments.create_invoice(cents, "Пополнение баланса")
    except Exception:
        await state.clear()
        return await message.answer("Не удалось создать счёт, попробуйте позже.")
    await db.create_invoice(invoice_id, message.from_user.id, "topup", cents, pay_url)
    await state.clear()
    await message.answer(
        f"🧾 Счёт на {texts.fmt_usd(cents)} создан. После оплаты нажмите «Проверить оплату».",
        reply_markup=pay_kb(pay_url, invoice_id))
