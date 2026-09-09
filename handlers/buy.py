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
    """Уведомление в админ-канал о покупке с реферальным вознаграждением."""
    from payments import percent_for_clients
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

    # Проверяем реферала и начисляем процент
    referrer_line = ""
    if user["referrer_id"]:
        ref = await db.get_user(user["referrer_id"])
        if ref:
            ref_id = user["referrer_id"]
            ref_link = f"tg://user?id={ref_id}"
            ref_uname = ref["username"]
            ref_mention = f'<a href="{ref_link}">@{ref_uname}</a>' if ref_uname else f'<a href="{ref_link}">#{ref_id}</a>'

            # Считаем процент по количеству клиентов реферера
            clients = await db.count_referral_clients(ref_id)
            percent = percent_for_clients(clients)

            if percent > 0 and price > 0:
                earn = int(price * percent / 100)
                try:
                    await db.add_referral_earning(ref_id, user_id, earn, percent, "purchase")
                    earn_text = f"+{texts.fmt_usd(earn)} ({percent}%)"
                except Exception:
                    earn_text = f"{percent}%"
            else:
                earn_text = "0% (порог не достигнут)"

            referrer_line = (
                f"\n━━━━━━━━━━━━━━━━━━\n"
                f"🤝 Реферер: {ref_mention}\n"
                f"📊 Уровень: {percent}% | Клиентов: {clients}\n"
                f"💸 Начислено рефереру: {earn_text}"
            )

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

    if config and getattr(config, "admin_group_id", None):
        try:
            await bot.send_message(config.admin_group_id, text, parse_mode="HTML")
        except Exception:
            pass

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
            if config and getattr(config, "admin_group_id", None):
                u_link = f"tg://user?id={user_id}"
                u_uname = user["username"] if user and "username" in user.keys() else None
                u_mention = f'<a href="{u_link}">@{u_uname}</a>' if u_uname else f'<a href="{u_link}">#{user_id}</a>'
                topup_text = (
                    f"💳 <b>Пополнение баланса!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💵 Сумма: <b>{texts.fmt_usd(result['amount'])}</b>\n"
                    f"👤 Пользователь: {u_mention}\n"
                    f"🆔 ID: <code>{user_id}</code>"
                )
                try:
                    await bot.send_message(config.admin_group_id, topup_text, parse_mode="HTML")
                except Exception:
                    pass
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

    # Проверяем обязательные каналы для покупки
    channels = await db.list_purchase_channels()
    if channels:
        missing = []
        for ch in channels:
            uname = ch['username']
            chat_id = uname if uname.startswith('@') else f"@{uname}"
            try:
                member = await bot.get_chat_member(chat_id, cb.from_user.id)
                if getattr(member, 'status', None) in ('left', 'kicked'):
                    missing.append(uname)
            except Exception:
                # Если не удалось проверить — требуем подписку на всякий случай
                missing.append(uname)
        if missing:
            mentions = ', '.join([('@' + u.lstrip('@')) for u in missing])
            links = '\n'.join([f"https://t.me/{u.lstrip('@')}" for u in missing])
            await cb.message.answer(
                f"Чтобы купить, подпишитесь на канал(ы): {mentions}\n{links}\nПосле подписки нажмите ещё раз.")
            return await cb.answer()

    user = await db.get_user(cb.from_user.id)
    stats = await db.get_user_stats(cb.from_user.id)
    loyalty = texts.get_loyalty_info(stats["total_spent_cents"])
    discount_p = loyalty.get("percent", 0)
    final_price = p["price"]
    if discount_p > 0:
        final_price = int(round(p["price"] * (100 - discount_p) / 100))

    price = texts.fmt_usd(final_price)
    discount_note = f" (со скидкой {discount_p}%)" if discount_p > 0 else ""

    if p["price"] == 0 or final_price == 0:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Получить бесплатно", callback_data=f"buyconfirm:{product_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"prod:{product_id}")],
        ])
        await cb.message.answer(f"«{p['name']}» — бесплатно. Подтвердите получение:", reply_markup=markup)
    elif user["balance"] >= final_price:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Оплатить {price} с баланса", callback_data=f"buyconfirm:{product_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"prod:{product_id}")],
        ])
        await cb.message.answer(f"Подтвердите покупку «{p['name']}» за {price}{discount_note}.", reply_markup=markup)
    else:
        rows = []
        if payments.enabled:
            if payments.cryptopay_enabled:
                rows.append([InlineKeyboardButton(text=f"🤖 CryptoBot (Карты / СБП / USDT) — {price}", callback_data=f"paydirect:{product_id}:cryptopay")])
            if payments.xrocket_enabled:
                rows.append([InlineKeyboardButton(text=f"🚀 xRocket (Карты / СБП / TON) — {price}", callback_data=f"paydirect:{product_id}:xrocket")])
            rows.append([InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup")])
            note = ""
        else:
            note = f"\n\n{texts.PAYMENTS_DISABLED}"
        currency = dict(user).get('currency', 'USD') if user else 'USD'
        await cb.message.answer(
            f"На балансе {texts.fmt_balance(user['balance'], currency)}, а товар стоит {price}{discount_note}.{note}\n\n"
            "Выберите способ оплаты (поддерживаются <b>СБП и банковские карты РФ</b> через P2P):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
            parse_mode="HTML"
        )
    await cb.answer()


@router.callback_query(F.data.startswith("buyconfirm:"))
async def buy_confirm(cb: CallbackQuery, db: Database, bot: Bot, config=None):
    product_id = int(cb.data.split(":")[1])
    p = await db.get_product(product_id)
    final_price = None
    if p:
        stats = await db.get_user_stats(cb.from_user.id)
        loyalty = texts.get_loyalty_info(stats["total_spent_cents"])
        discount_p = loyalty.get("percent", 0)
        if discount_p > 0:
            final_price = int(round(p["price"] * (100 - discount_p) / 100))

    result = await db.buy_with_balance(cb.from_user.id, product_id, final_price=final_price)
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
    
    parts = cb.data.split(":")
    product_id = int(parts[1])
    provider = parts[2] if len(parts) > 2 else ("cryptopay" if payments.cryptopay_enabled else "xrocket")

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
        invoice_id, pay_url = await payments.create_invoice(p["price"], f"Покупка: {p['name']}", provider=provider)
    except Exception as e:
        if item_id:
            await db.release_item(item_id)
        return await cb.answer(f"Не удалось создать счёт ({e})", show_alert=True)
    
    await db.create_invoice(invoice_id, cb.from_user.id, "purchase", p["price"], pay_url,
                            product_id=product_id, item_id=item_id, provider=provider)
    
    prov_name = "xRocket" if provider == "xrocket" else "CryptoBot"
    msg_text = (
        f"🧾 <b>Счёт на {texts.fmt_usd(p['price'])} ({prov_name}) создан</b>\n\n"
        "⏳ Срок действия: 30 минут (товар зарезервирован).\n\n"
        "💡 <i>Нет крипты? При переходе по ссылке оплаты вы можете моментально оплатить с карты РФ (СБП, Сбер, Т-Банк) через P2P внутри Telegram!</i>\n\n"
        "После завершения платежа нажмите «🔄 Проверить оплату»."
    )
    await cb.message.answer(msg_text, reply_markup=pay_kb(pay_url, invoice_id), parse_mode="HTML")
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
    
    statuses = await payments.get_statuses([inv])
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

    # Если доступны оба провайдера — предлагаем выбор
    if payments.cryptopay_enabled and payments.xrocket_enabled:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 CryptoBot (Карты РФ / СБП / USDT)", callback_data=f"topup_prov:cryptopay:{cents}")],
            [InlineKeyboardButton(text="🚀 xRocket (Карты РФ / СБП / TON)", callback_data=f"topup_prov:xrocket:{cents}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:profile")],
        ])
        await state.clear()
        return await message.answer(
            f"Сумма к пополнению: <b>{texts.fmt_usd(cents)}</b>\n\n"
            "Выберите удобный способ оплаты (поддерживаются <b>карты РФ и СБП</b> через P2P):",
            reply_markup=markup,
            parse_mode="HTML"
        )

    # Если доступен только один — создаем сразу
    provider = "xrocket" if payments.xrocket_enabled else "cryptopay"
    try:
        invoice_id, pay_url = await payments.create_invoice(cents, "Пополнение баланса", provider=provider)
    except Exception as e:
        await state.clear()
        return await message.answer(f"Не удалось создать счёт ({e}), попробуйте позже.")
    await db.create_invoice(invoice_id, message.from_user.id, "topup", cents, pay_url, provider=provider)
    await state.clear()
    
    prov_name = "xRocket" if provider == "xrocket" else "CryptoBot"
    msg_text = (
        f"🧾 <b>Счёт на {texts.fmt_usd(cents)} ({prov_name}) создан</b>\n\n"
        "💡 <i>Нет крипты? При переходе по ссылке вы можете оплатить любой картой РФ (СБП, Сбер, Т-Банк) через встроенный P2P без комиссий!</i>\n\n"
        "После оплаты нажмите «🔄 Проверить оплату»."
    )
    await message.answer(msg_text, reply_markup=pay_kb(pay_url, invoice_id), parse_mode="HTML")


@router.callback_query(F.data.startswith("topup_prov:"))
async def topup_provider_selected(cb: CallbackQuery, db: Database, payments: Payments, state: FSMContext):
    parts = cb.data.split(":")
    provider = parts[1]
    cents = int(parts[2])
    
    try:
        invoice_id, pay_url = await payments.create_invoice(cents, "Пополнение баланса", provider=provider)
    except Exception as e:
        return await cb.answer(f"Ошибка создания счёта: {e}", show_alert=True)
        
    await db.create_invoice(invoice_id, cb.from_user.id, "topup", cents, pay_url, provider=provider)
    prov_name = "xRocket" if provider == "xrocket" else "CryptoBot"
    
    msg_text = (
        f"🧾 <b>Счёт на {texts.fmt_usd(cents)} ({prov_name}) создан</b>\n\n"
        "💡 <i>Нет крипты? При переходе по ссылке вы можете оплатить любой картой РФ (СБП, Сбер, Т-Банк) через встроенный P2P без комиссий!</i>\n\n"
        "После оплаты нажмите «🔄 Проверить оплату»."
    )
    await cb.message.answer(msg_text, reply_markup=pay_kb(pay_url, invoice_id), parse_mode="HTML")
    await cb.answer()
