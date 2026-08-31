"""
Обработчик пользователя для ОСНОВНОГО БОТА (без чеков, зеркал, мини приложений)
"""
from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
                           ReplyKeyboardRemove)

import keyboards
import random
import texts
from config import Config
from db import Database
from handlers.buy import deliver
from media import send_media, send_product_photos, send_tab, send_menu
from payments import percent_for_clients

router = Router()


class SearchState(StatesGroup):
    query = State()


def menu_only_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[keyboards.menu_row()])


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    """Do nothing - for disabled buttons"""
    await cb.answer()


@router.callback_query(F.data.in_({"check_subscription", "check_mirror_subscription"}))
async def check_subscription(cb: CallbackQuery, db: Database, bot: Bot, mirror: dict | None = None):
    """Проверяет подписку когда пользователь нажал «Я подписался»"""
    # Получаем список обязательных каналов
    channels = await db.list_required_channels()
    ch_list = []
    if mirror:
        if mirror.get("channel_username"):
            ch_list.append({"username": mirror["channel_username"], "link": mirror.get("channel_link") or f"https://t.me/{mirror['channel_username']}"})
    for ch in channels:
        ch_list.append({"username": ch["username"], "link": f"https://t.me/{ch['username']}"})

    # Если пуст — разрешаем доступ
    if not ch_list:
        await cb.answer("✅ Доступ открыт!", show_alert=False)
        markup = await keyboards.main_menu(db)
        await send_menu(cb.message, db, texts.MENU, markup)
        return

    missing = []
    for ch in ch_list:
        try:
            member = await bot.get_chat_member(f"@{ch['username']}", cb.from_user.id)
            is_subscribed = member.status in ("member", "administrator", "creator")
        except Exception:
            is_subscribed = False
        if not is_subscribed:
            missing.append(ch)

    if not missing:
        await cb.answer("✅ Подписка подтверждена!", show_alert=False)
        try:
            await cb.message.delete()
        except Exception:
            pass
        # Показываем главное меню
        markup = await keyboards.main_menu(db)
        await send_menu(cb.message, db, texts.MENU, markup)
    else:
        await cb.answer(
            "❌ Вы ещё не подписались на все необходимые каналы!\nПодпишитесь и нажмите кнопку снова.",
            show_alert=True
        )



@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, db: Database, state: FSMContext, bot: Bot, config, mirror: dict | None = None):
    await state.clear()

    # ─── Парсим реферера из аргументов ───
    referrer_id = None
    if command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args[4:])
        except ValueError:
            referrer_id = None

    # ─── Регистрируем пользователя ПЕРВЫМ (чтобы реферер всегда сохранился) ───
    existing = await db.get_user(message.from_user.id)
    await db.get_or_create_user(message.from_user.id, message.from_user.username, referrer_id)

    # Если пользователь новый И пришёл по рефке — уведомляем админа
    if not existing and referrer_id:
        referrer = await db.get_user(referrer_id)
        if referrer:
            uid = message.from_user.id
            uname = message.from_user.username
            user_link = f"tg://user?id={uid}"
            user_mention = f'<a href="{user_link}">@{uname}</a>' if uname else f'<a href="{user_link}">#{uid}</a>'

            ref_link = f"tg://user?id={referrer_id}"
            ref_uname = referrer["username"]
            ref_mention = f'<a href="{ref_link}">@{ref_uname}</a>' if ref_uname else f'<a href="{ref_link}">#{referrer_id}</a>'

            notify_text = (
                f"🤝 <b>Новый реферал!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 Пользователь: {user_mention}\n"
                f"🆔 ID: <code>{uid}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔗 Пришёл от: {ref_mention}\n"
                f"🆔 ID реферера: <code>{referrer_id}</code>"
            )
            try:
                if config and getattr(config, "admin_group_id", None):
                    await bot.send_message(config.admin_group_id, notify_text, parse_mode="HTML")
                admin_id = await db.get_setting("admin_id")
                if admin_id:
                    await bot.send_message(int(admin_id), notify_text, parse_mode="HTML")
            except Exception:
                pass
    # ─────────────────────────────────────────────────────────────────────────

    # Активация чека через аргумент /start chk_...
    if command.args and command.args.startswith("chk_"):
        from handlers.checks_promos import handle_check_start
        await handle_check_start(message, command.args, db)
        return

    # ─── Deep-link на товар /start prod_<id> ───
    if command.args and command.args.startswith("prod_"):
        try:
            pid = int(command.args[5:])
        except ValueError:
            pid = None

        if pid is not None:
            p = await db.get_product(pid)
            if p and p["visible"]:
                from media import send_product_photos
                import texts as _texts

                buy_markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=f"🛒 Купить — {_texts.fmt_usd(p['price'])}",
                        callback_data=f"buy:{pid}"
                    )],
                    [InlineKeyboardButton(text="🛍️ Каталог", callback_data="menu:catalog")],
                    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main")],
                ])
                caption = (
                    f"📦 <b>{p['name']}</b>\n\n"
                    f"{p['description']}\n\n"
                    f"💵 Цена: <b>{_texts.fmt_usd(p['price'])}</b>"
                )
                photos = await db.list_product_photos(pid)
                await send_product_photos(message, photos, caption, buy_markup)
                return
            else:
                await message.answer("❌ Товар не найден или временно недоступен.")
                return
    # ───────────────────────────────────────────


    # Проверяем рекламу в приветствии
    welcome_ad = await db.get_active_welcome_ad()
    ad_block = f"\n\n⭐ <b>СПОНСОР:</b>\n{welcome_ad['text_content']}" if welcome_ad else ""
    welcome_text = texts.WELCOME + ad_block
    await message.answer(welcome_text, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")

    markup = await keyboards.main_menu(db)
    await send_menu(message, db, texts.MENU, markup)


@router.callback_query(F.data == "menu:more")
async def more_menu(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    our_projects_url = await db.get_setting("link:our_projects_url")

    async def g(key: str, default: str) -> str:
        v = await db.get_setting(f"btn:{key}")
        return v or default

    s_history = await g("history", "💎 История")
    s_referral = await g("referral", "💎 Рефералка")
    s_check = await g("create_check", "💎 Создать чек")
    s_promo = await g("promocode", "💎 Промокод")
    s_ads = await g("ads", "💎 Реклама")
    s_about = await g("about", "💎 О магазине")

    rows = [
        [InlineKeyboardButton(text=s_history, callback_data="menu:history"),
         InlineKeyboardButton(text=s_referral, callback_data="menu:referral")],
        [InlineKeyboardButton(text=s_ads, callback_data="menu:ads")],
        [InlineKeyboardButton(text=s_check, callback_data="create_check_btn"),
         InlineKeyboardButton(text=s_promo, callback_data="activate_promo_btn")],
    ]
    if our_projects_url and our_projects_url.strip() and our_projects_url.strip() != "https://t.me/":
        rows.append([InlineKeyboardButton(text="❇️ Наши проекты", url=our_projects_url.strip())])
    rows.append([InlineKeyboardButton(text=s_about, callback_data="menu:about")])
    rows.append([InlineKeyboardButton(text="💎 Главное меню", callback_data="menu:main")])

    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    await send_tab(cb.message, db, "video:tab:more", "⚙️ <b>Дополнительное меню:</b>", markup, banner_suffix="more")
    await cb.answer()

@router.callback_query(F.data == "menu:catalog")
async def catalog(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    cats = await db.list_categories()
    rows = [[InlineKeyboardButton(text=cat["name"], callback_data=f"cat:{cat['id']}:0")] for cat in cats]
    rows.append(keyboards.menu_row())
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    await send_tab(cb.message, db, "video:tab:catalog", f"📁 Каталог ({len(cats)} разделов):",
                   markup, banner_suffix="catalog")
    await cb.answer()


@router.callback_query(F.data.startswith("cat:"))
async def open_category(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    parts = cb.data.split(":")
    if len(parts) < 3:
        await cb.answer()
        return
    
    cat_id = int(parts[1])
    page = int(parts[2])
    
    cat = await db.get_category(cat_id)
    if not cat:
        await cb.answer("Категория не найдена", show_alert=True)
        return
    
    subcats = await db.list_subcategories(cat_id)
    prods = await db.list_products(cat_id)
    
    rows = []
    # Сначала выводим кнопки вложенных подразделов (если есть)
    if subcats:
        for sc in subcats:
            sub_count = await db.count_products(sc["id"])
            count_str = f" ({sub_count})" if sub_count else ""
            rows.append([InlineKeyboardButton(text=f"📂 {sc['name']}{count_str}", callback_data=f"cat:{sc['id']}:0")])

    ITEMS_PER_PAGE = 6
    total_pages = (len(prods) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if prods else 1
    
    if page < 0 or page >= total_pages:
        page = 0
    
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_prods = prods[start_idx:end_idx] if prods else []
    
    for p in page_prods:
        rows.append([InlineKeyboardButton(text=f"📦 {p['name']} — {texts.fmt_usd(p['price'])}",
                                          callback_data=f"prod:{p['id']}")])
    
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"cat:{cat_id}:{page-1}"))
        else:
            pagination_buttons.append(InlineKeyboardButton(text="◀️", callback_data="noop"))
        
        pagination_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
        
        if page < total_pages - 1:
            pagination_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"cat:{cat_id}:{page+1}"))
        else:
            pagination_buttons.append(InlineKeyboardButton(text="▶️", callback_data="noop"))
        
        rows.append(pagination_buttons)
    
    # Кнопка возврата: к родителю или в главный каталог
    if "parent_id" in cat.keys() and cat["parent_id"]:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat:{cat['parent_id']}:0")])
    else:
        rows.append([InlineKeyboardButton(text="⬅️ Каталог", callback_data="menu:catalog")])
    rows.append(keyboards.menu_row())
    
    desc = cat["description"].strip() if ("description" in cat.keys() and cat["description"]) else ""
    desc_block = f"\n\n📝 {desc}" if desc else ""

    if subcats and prods:
        text = f"📁 <b>{cat['name']}</b>{desc_block}\n\nВыберите подраздел или товар:"
    elif subcats:
        text = f"📁 <b>{cat['name']}</b>{desc_block}\n\nВыберите подраздел ({len(subcats)}):"
    elif prods:
        text = f"📁 <b>{cat['name']}</b>{desc_block}\n\nВыберите товар ({len(page_prods)} из {len(prods)}):"
    else:
        text = f"📁 <b>{cat['name']}</b>{desc_block}\n\nЗдесь пока нет товаров или подразделов."

    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if "video_file_id" in cat.keys() and cat["video_file_id"]:
        try:
            await send_media(cb.message, cat["video_file_id"], text, markup)
        except Exception:
            await cb.message.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        await cb.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("prod:"))
async def product_card(cb: CallbackQuery, db: Database):
    try:
        parts = cb.data.split(":")
        if len(parts) < 2:
            await cb.answer("Ошибка: неверная структура данных")
            return
            
        prod_id = int(parts[1])
        prod = await db.get_product(prod_id)
        if not prod:
            await cb.answer("Товар не найден", show_alert=True)
            return
        
        lines = [f"📦 {prod['name']}", f"💵 Цена: {texts.fmt_usd(prod['price'])}"]
        if prod['description']:
            desc = prod['description'][:500]  # Ограничиваем описание 500 символов
            if len(prod['description']) > 500:
                desc += "..."
            lines.append(f"\n📝 Описание:\n{desc}")
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить", callback_data=f"buynow:{prod_id}")],
            [InlineKeyboardButton(text="⭐ Отзывы", callback_data=f"reviews:{prod_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat:{prod['category_id']}:0")],
            keyboards.menu_row(),
        ])
        
        text = "\n".join(lines)
        photos = await db.list_product_photos(prod_id)
        if photos:
            await send_product_photos(cb.message, photos, text, markup)
        else:
            await cb.message.answer(text, reply_markup=markup)
        await cb.answer()
    except Exception as e:
        await cb.answer(f"Ошибка: {str(e)}", show_alert=True)
        raise


@router.callback_query(F.data.startswith("reviews:"))
async def product_reviews(cb: CallbackQuery, db: Database):
    prod_id = int(cb.data.split(":")[1])
    prod = await db.get_product(prod_id)
    if not prod:
        await cb.answer("Товар не найден", show_alert=True)
        return
    
    reviews = await db.list_reviews(prod_id)
    if not reviews:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать отзыв", callback_data="write_review")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"prod:{prod_id}")],
            keyboards.menu_row(),
        ])
        await cb.message.answer(
            f"📦 {prod['name']}\n\n⭐ Отзывов нет. Будьте первыми!",
            reply_markup=markup
        )
        await cb.answer()
        return
    
    lines = [f"📦 {prod['name']}\n⭐ Отзывы:\n"]
    for rev in reviews[:5]:
        stars = "⭐" * rev["rating"]
        lines.append(f"\n{stars} @{rev['username'] or 'аноним'}")
        lines.append(f"💬 {rev['text']}")
    
    if len(reviews) > 5:
        lines.append(f"\n... и еще {len(reviews) - 5} отзывов")
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Написать отзыв", callback_data="write_review")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"prod:{prod_id}")],
        keyboards.menu_row(),
    ])
    await cb.message.answer("\n".join(lines), reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data == "menu:profile")
async def profile(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    user = await db.get_or_create_user(cb.from_user.id, cb.from_user.username)
    stats = await db.get_user_stats(cb.from_user.id)
    loyalty = texts.get_loyalty_info(stats["total_spent_cents"])

    try:
        currency = user['currency'] if user else 'USD'
    except Exception:
        currency = 'USD'

    # Форматирование даты регистрации
    reg_raw = user["created_at"] if user and "created_at" in dict(user) and user["created_at"] else "2025-10-30"
    try:
        reg_parts = reg_raw.split()[0].split('-')
        reg_formatted = f"{reg_parts[2]}.{reg_parts[1]}.{reg_parts[0]}"
    except Exception:
        reg_formatted = "30.10.2025"

    username_str = f"@{user['username']}" if user and user['username'] else f"id{cb.from_user.id}"

    # Синхронизация контейнеров
    await db.sync_user_containers(cb.from_user.id)
    container_info = await db.get_container_info(cb.from_user.id)

    text = (
        f"🌀 <b>Профиль</b>\n\n"
        f"🔘 <b>Аккаунт</b>\n"
        f"├ Никнейм: {username_str}\n"
        f"├ ID: <code>{cb.from_user.id}</code>\n"
        f"└ Регистрация: {reg_formatted}\n\n"
        f"📉 <b>Статистика</b>\n"
        f"├ Всего заказов: {stats['total_orders']}\n"
        f"├ Выполнено: {stats['completed_orders']}\n"
        f"└ Потрачено: {texts.fmt_rub_amount(loyalty['spent_rub'])}\n\n"
        f"🪙 <b>Финансы</b>\n"
        f"└ Баланс: {texts.fmt_balance(user['balance'], currency)}\n\n"
        f"💲 <b>Личная скидка</b>\n"
        f"├ Статус: {loyalty['name']}\n"
        f"└ Скидка: {loyalty['percent']:.2f}%\n\n"
        f"📦 Контейнеры: {container_info['available']} доступно | {container_info['opened']} открыто"
    )

    buttons = [
        [InlineKeyboardButton(text="💲 Личная скидка", callback_data="profile:discount")],
        [InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text=f"💱 Валюта: {currency}", callback_data="profile:currency")],
    ]

    if container_info['available'] > 0:
        buttons.append([InlineKeyboardButton(text=f"🔓 Открыть контейнер ({container_info['available']})", callback_data="containers:open")])
    
    buttons.append([InlineKeyboardButton(text="📦 Все контейнеры", callback_data="menu:containers")])
    buttons.append(keyboards.menu_row())
    
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_tab(cb.message, db, "video:tab:profile", text, markup, banner_suffix="profile")
    await cb.answer()


@router.callback_query(F.data == "profile:discount")
async def profile_discount(cb: CallbackQuery, db: Database):
    user = await db.get_user(cb.from_user.id)
    stats = await db.get_user_stats(cb.from_user.id)
    loyalty = texts.get_loyalty_info(stats["total_spent_cents"])

    spent_fmt = texts.fmt_rub_amount(loyalty["spent_rub"])
    if loyalty["next_name"]:
        target_fmt = texts.fmt_rub_amount(loyalty["next_target_rub"])
        needed_fmt = texts.fmt_rub_amount(loyalty["needed_rub"])
        spent_line = f"├ Потрачено: {spent_fmt} / {target_fmt}"
        next_line = f"└ До уровня «{loyalty['next_name']}»: {needed_fmt}"
    else:
        spent_line = f"├ Потрачено: {spent_fmt}"
        next_line = "└ Достигнут максимальный уровень!"

    text = (
        f"💲 <b>Личная скидка</b>\n\n"
        f"Получайте постоянную скидку, повышая свой уровень покупателя. Уровень рассчитывается автоматически по общей сумме выполненных заказов.\n\n"
        f"<b>Ваш статус</b>\n"
        f"├ Уровень: {loyalty['name']}\n"
        f"├ Личная скидка: {loyalty['percent']:.2f}%\n"
        f"{spent_line}\n"
        f"{next_line}\n\n"
        f"<b>Уровни личной скидки</b>\n\n"
        f"🥉 <b>Бронза — 0%</b>\n"
        f"└ Сумма покупок от 0 ₽\n\n"
        f"🥈 <b>Серебро — 2.50%</b>\n"
        f"└ Сумма покупок от 10 000 ₽\n\n"
        f"🥇 <b>Золото — 5%</b>\n"
        f"└ Сумма покупок от 25 000 ₽\n\n"
        f"💎 <b>Платина — 10%</b>\n"
        f"└ Сумма покупок от 50 000 ₽\n\n"
        f"<i>При достижении новой суммы статус обновится автоматически.</i>"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад в профиль", callback_data="menu:profile")]
    ])

    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "menu:history")
async def history(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    purchases = await db.list_purchases(cb.from_user.id, limit=10)
    if not purchases:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:more")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
        ])
        try:
            await cb.message.edit_text("📜 У вас пока нет покупок.", reply_markup=markup)
        except Exception:
            await cb.message.answer("📜 У вас пока нет покупок.", reply_markup=markup)
        return await cb.answer()
    
    lines = ["📜 Ваши покупки:", ""]
    rows = []
    for p in purchases:
        lines.append(f"📦 {p['product_name']}")
        lines.append(f"   💵 Цена: {texts.fmt_usd(p['price'])}")
        lines.append(f"   📅 Дата: {p['created_at'][:16]}")
        lines.append("")
        rows.append([InlineKeyboardButton(text=f"🔄 {p['product_name']}", callback_data=f"again:{p['id']}")])
    
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:more")])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")])
    try:
        await cb.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception:
        await cb.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data.startswith("again:"))
async def purchase_again(cb: CallbackQuery, db: Database, bot: Bot):
    purchase = await db.get_purchase(int(cb.data.split(":")[1]))
    if not purchase or purchase["user_id"] != cb.from_user.id:
        return await cb.answer("Покупка не найдена", show_alert=True)
    await deliver(bot, cb.from_user.id, purchase["product_name"],
                  purchase["content_type"], purchase["content_value"])
    await cb.answer()


@router.callback_query(F.data == "menu:referral")
async def referral(cb: CallbackQuery, db: Database, bot: Bot, state: FSMContext):
    await state.clear()
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{cb.from_user.id}"
    invited = await db.count_invited(cb.from_user.id)
    clients = await db.count_referral_clients(cb.from_user.id)
    earned = await db.total_referral_earned(cb.from_user.id)
    user = await db.get_or_create_user(cb.from_user.id, cb.from_user.username)
    currency = dict(user).get('currency', 'USD') if user else 'USD'
    text = texts.REFERRAL.format(
        link=link,
        invited=invited,
        percent=percent_for_clients(clients),
        earned=texts.fmt_balance(earned, currency)
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Поделиться ссылкой",
                              url=f"https://t.me/share/url?url={link}&text=Присоединяйся%20к%20магазину!")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:more")],
    ])
    try:
        await send_tab(cb.message, db, "video:tab:referral", text, markup, banner_suffix="referral")
    except Exception:
        try:
            await cb.message.edit_text(text, reply_markup=markup)
        except Exception:
            await cb.message.answer(text, reply_markup=markup)
    await cb.answer()



@router.callback_query(F.data == "menu:search")
async def search_start(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    await state.set_state(SearchState.query)
    await send_tab(cb.message, db, "video:tab:search", "🔍 Введите название или описание товара:",
                   menu_only_kb(), banner_suffix="search")
    await cb.answer()


@router.message(SearchState.query, F.text)
async def search_run(message: Message, db: Database, state: FSMContext):
    await state.clear()
    query = message.text.strip()
    if not query:
        return await message.answer("Пустой запрос. Откройте «🔍 Поиск» и попробуйте снова.",
                                    reply_markup=menu_only_kb())
    products = await db.search_products(query)
    if not products:
        return await message.answer("😕 Ничего не найдено. Попробуйте другой запрос.",
                                    reply_markup=menu_only_kb())
    rows = [[InlineKeyboardButton(text=f"{p['name']} — {texts.fmt_usd(p['price'])}",
                                  callback_data=f"prod:{p['id']}")] for p in products[:20]]
    rows.append(keyboards.menu_row())
    await message.answer(f"🔍 Найдено товаров: {len(products)}",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


class ReviewState(StatesGroup):
    product_id = State()
    rating = State()
    text = State()


@router.callback_query(F.data == "menu:about")
async def about_project(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    
    # Загружаем каналы из БД
    db_channels = await db.list_about_channels()
    our_projects_url = await db.get_setting("link:our_projects_url")

    rows = [
        [InlineKeyboardButton(text="📚 FAQ", callback_data="about:faq")]
    ]

    # Если задана отдельная ссылка на Наши проекты
    if our_projects_url and our_projects_url.strip() and our_projects_url.strip() != "https://t.me/":
        rows.append([InlineKeyboardButton(text="❇️ Наши проекты", url=our_projects_url.strip())])

    # Если есть каналы в БД
    if db_channels:
        for ch in db_channels:
            uname = ch["username"] or ""
            title = ch["title"] or (f"@{uname}" if uname else "Канал")
            url = ch["url"] or (f"https://t.me/{uname}" if uname else None)
            if url:
                rows.append([InlineKeyboardButton(text=title, url=url)])
    else:
        # Стандартные каналы по умолчанию, если админ ещё не добавил свои
        rows.extend([
            [InlineKeyboardButton(text="📺 Реклама", url="https://t.me/glock_price")],
            [InlineKeyboardButton(text="📰 Новостной канал", url="https://t.me/news_glock_shop")],
            [InlineKeyboardButton(text="⭐ Отзывы", url="https://t.me/reps_glock_shop")],
        ])

    rows.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main")])

    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await cb.message.edit_text(texts.ABOUT_PROJECT, reply_markup=markup)
    except Exception:
        await cb.message.answer(texts.ABOUT_PROJECT, reply_markup=markup)
    await cb.answer()

@router.callback_query(F.data == "about:faq")
async def about_faq(cb: CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[
       [InlineKeyboardButton(text="⬅️ Назад к О магазине", callback_data="menu:about")],
       [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    ])
    try:
        await cb.message.edit_text(texts.FAQ_TEXT, reply_markup=markup)
    except Exception:
        await cb.message.answer(texts.FAQ_TEXT, reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data == "write_review")
async def write_review_start(cb: CallbackQuery, state: FSMContext, db: Database):
    purchases = await db.list_purchases(cb.from_user.id, limit=20)
    if not purchases:
       await cb.message.answer("❌ Вы пока ничего не купили. Напишите отзыв после первой покупки!",
                              reply_markup=menu_only_kb())
       return await cb.answer()
    
    rows = [[InlineKeyboardButton(text=f"⭐ {p['product_name']} - {texts.fmt_usd(p['price'])}",
                                callback_data=f"review:select:{p['id']}")] for p in purchases]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")])
    await cb.message.answer("Выберите товар, на который хотите написать отзыв:",
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data.startswith("review:select:"))
async def review_select_product(cb: CallbackQuery, state: FSMContext, db: Database):
    purchase_id = int(cb.data.split(":")[2])
    purchase = await db.get_purchase(purchase_id)
    
    if not purchase or purchase["user_id"] != cb.from_user.id:
       return await cb.answer("Покупка не найдена", show_alert=True)
    
    await state.set_state(ReviewState.product_id)
    await state.update_data(product_id=purchase["product_id"], product_name=purchase["product_name"])
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
       [InlineKeyboardButton(text="⭐", callback_data="review:rating:1"),
        InlineKeyboardButton(text="⭐⭐", callback_data="review:rating:2"),
        InlineKeyboardButton(text="⭐⭐⭐", callback_data="review:rating:3"),
        InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data="review:rating:4"),
        InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data="review:rating:5")],
    ])
    await cb.message.answer("Оцените товар (1-5 звёзд):", reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data.startswith("review:rating:"))
async def review_select_rating(cb: CallbackQuery, state: FSMContext):
    rating = int(cb.data.split(":")[2])
    await state.update_data(rating=rating)
    await state.set_state(ReviewState.text)
    await cb.message.answer("Напишите ваш отзыв (минимум 10 символов):")
    await cb.answer()


@router.message(ReviewState.text, F.text)
async def review_submit(message: Message, db: Database, state: FSMContext, bot: Bot, config: Config):
    text = message.text.strip()
    if len(text) < 10:
       await message.answer("Отзыв слишком короткий. Минимум 10 символов:")
       return
    
    data = await state.get_data()
    product_id = data.get("product_id")
    product_name = data.get("product_name")
    rating = data.get("rating", 0)
    
    await db.add_review(message.from_user.id, message.from_user.username, 
                       product_id, product_name, text, rating)
    
    # Отправляем отзыв в канал отзывов
    stars = "⭐" * rating
    review_text = (f"{stars}\n\n"
                 f"👤 @{message.from_user.username or 'неизвестен'}\n"
                 f"📦 {product_name}\n\n"
                 f"💬 {text}")
    
    try:
       await bot.send_message(config.reviews_channel_id, review_text)
    except Exception:
       pass
    
    # Логируем отзыв
    await db.add_log(message.from_user.id, message.from_user.username, 
                    "написал_отзыв", f"{product_name} ({rating} звёзд)")
    
    await state.clear()
    await message.answer("✅ Спасибо за ваш отзыв! Он опубликован в канале отзывов.",
                        reply_markup=menu_only_kb())


@router.callback_query(F.data == "menu:containers")
async def menu_containers(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    # Синхронизируем контейнеры по потраченным средствам
    await db.sync_user_containers(cb.from_user.id)
    info = await db.get_container_info(cb.from_user.id)
    text = (
        "📦 Контейнеры\n\n"
        "Получайте 1 контейнер за каждые 1 000 ₽, потраченные в магазине.\n\n"
        f"Ваши контейнеры\n| Доступно: {info['available']}\n| Всего получено: {info['total_received']}\n| Уже открыто: {info['opened']}\n| До следующего: {info['to_next_rub']:.2f} ₽\n\n"
        "Внутри может быть денежный приз: 10 ₽, 25 ₽, 50 ₽ или 99 ₽. Награда моментально зачисляется на баланс."
    )
    
    buttons = [
        [InlineKeyboardButton(text="📜 История контейнеров", callback_data="containers:history")],
    ]
    if info['available'] > 0:
        buttons.append([InlineKeyboardButton(text="🔓 Открыть контейнер", callback_data="containers:open")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="menu:profile")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:
        await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data == "containers:open")
async def containers_open(cb: CallbackQuery, db: Database):
    rewards = [10, 25, 50, 99]
    reward = random.choice(rewards)
    res = await db.open_container(cb.from_user.id, reward)
    if res.get("status") == "no_available":
        return await cb.answer("У вас нет доступных контейнеров.", show_alert=True)
    text = f"🎉 Вы открыли контейнер и получили {reward} ₽! Средства зачислены на баланс."
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📦 Вернуться к контейнерам", callback_data="menu:containers")]])
    await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data == "containers:history")
async def containers_history(cb: CallbackQuery, db: Database):
    rows = await db.list_container_history(cb.from_user.id, limit=20)
    if not rows:
        await cb.message.answer("📜 История контейнеров пуста.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:profile")]]))
        return await cb.answer()
    lines = ["📜 История контейнеров:\n"]
    for r in rows:
        lines.append(f"{r['created_at']}: {r['event']} — {r['amount_rub']} ₽ {r['details'] or ''}")
    await cb.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:profile")]]))
    await cb.answer()


@router.callback_query(F.data == "menu:main")
async def menu_main(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    markup = await keyboards.main_menu(db)
    await send_menu(cb.message, db, texts.MENU, markup)
    await cb.answer()


@router.callback_query(F.data == "menu:support")
async def menu_support(cb: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    support_url = await db.get_setting("link:support_url") or await db.get_setting("link:support")
    backup_url = await db.get_setting("link:support_backup_url") or "https://t.me/glock_admin_bot"

    buttons = []
    if support_url and support_url.strip() and support_url.strip() != "https://t.me/":
        buttons.append([InlineKeyboardButton(text="💬 Основная поддержка", url=support_url.strip())])
    
    if backup_url and backup_url.strip():
        buttons.append([InlineKeyboardButton(text="🆘 Резервная поддержка (@glock_admin_bot)", url=backup_url.strip())])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = (
        "💬 <b>СЛУЖБА ПОДДЕРЖКИ</b>\n\n"
        "Если у вас возникли вопросы, трудности с оплатой или получением товара — мы на связи!\n\n"
        "⏰ <b>Режим работы:</b> 24/7\n"
        "⚡ <b>Среднее время ответа:</b> 5–10 минут\n\n"
        "📌 <i>Если основная техподдержка не отвечает — обязательно напишите в нашего резервного бота поддержки:</i>\n"
        "👉 @glock_admin_bot"
    )
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()


# --- Смена валюты для пользователя ---
@router.callback_query(F.data == "profile:currency")
async def profile_currency(cb: CallbackQuery, db: Database):
    user = await db.get_or_create_user(cb.from_user.id, cb.from_user.username)
    curr = user['currency'] if user and 'currency' in user.keys() else 'USD'
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 USD", callback_data="profile:currency:set:USD")],
        [InlineKeyboardButton(text="₽ RUB", callback_data="profile:currency:set:RUB")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:profile")],
    ])
    await cb.message.answer(f"Текущая валюта: {curr}. Выберите новую:", reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data.startswith("profile:currency:set:"))
async def profile_currency_set(cb: CallbackQuery, db: Database):
    parts = cb.data.split(":")
    newc = parts[-1]
    if newc not in ("USD", "RUB"):
        return await cb.answer("Неизвестная валюта", show_alert=True)
    await db.set_user_currency(cb.from_user.id, newc)
    await cb.answer(f"Валюта изменена на {newc}")
    user = await db.get_or_create_user(cb.from_user.id, cb.from_user.username)
    count = await db.count_purchases(cb.from_user.id)
    currency = dict(user).get('currency', 'USD') if user else 'USD'
    text = (f"👤 Профиль\n\n🆔 ID: {cb.from_user.id}\n"
            f"💰 Баланс: {texts.fmt_balance(user['balance'], currency)}\n🛒 Покупок: {count}")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💱 Валюта: {currency}", callback_data="profile:currency")],
        [InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup")],
        keyboards.menu_row(),
    ])
    await cb.message.answer(text, reply_markup=markup)


# Команды админки - только для основного бота (без зеркал)
@router.message(F.text == "/admin")
async def cmd_admin(message: Message, config, state: FSMContext):
    """Команда /admin - только основной админ"""
    if message.from_user.username and config.admin_username and \
       message.from_user.username.lower() == config.admin_username.lower():
        from handlers.admin import admin_menu_kb
        await state.clear()
        await message.answer("⚙️ Админ-панель", reply_markup=admin_menu_kb())
    else:
        await message.answer("❌ У вас нет доступа к админке.")
