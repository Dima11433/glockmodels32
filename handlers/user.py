from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
                           ReplyKeyboardRemove)

import keyboards
import texts
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


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, db: Database, state: FSMContext, bot: Bot, config, mirror: dict | None = None):
    await state.clear()

    # Активация чека через реферальный аргумент /start chk_...
    if command.args and command.args.startswith("chk_"):
        from handlers.checks_promos import handle_check_start
        await handle_check_start(message, command.args, db)
        return

    # Переход к конкретному товару по deep-link /start prod_<id>
    if command.args and command.args.startswith("prod_"):
        try:
            pid = int(command.args[5:])
        except ValueError:
            pid = None

        if pid is not None:
            p = await db.get_product(pid)
            if p and p["visible"]:
                from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                from media import send_product_photos

                # Сначала отправляем фото (если есть) — отдельным блоком
                try:
                    await send_product_photos(message, db, pid)
                except Exception:
                    pass

                # Карточка товара
                buy_markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=f"🛒 Купить — {texts.fmt_usd(p['price'])}",
                        callback_data=f"buy:{pid}"
                    )],
                    [InlineKeyboardButton(text="⬅️ В каталог", callback_data="menu:catalog")],
                ])
                await message.answer(
                    f"📦 <b>{p['name']}</b>\n\n"
                    f"{p['description']}\n\n"
                    f"💵 Цена: <b>{texts.fmt_usd(p['price'])}</b>",
                    reply_markup=buy_markup,
                    parse_mode="HTML"
                )
                return
            else:
                await message.answer("❌ Товар недоступен или не найден.")
                return


    referrer_id = None
    if command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args[4:])
        except ValueError:
            referrer_id = None
    await db.get_or_create_user(message.from_user.id, message.from_user.username, referrer_id)
    
    # Проверяем подписку на канал зеркала (если он настроен)
    should_subscribe = False
    channel_link = None
    if mirror:
        # Преобразуем Row в dict для удобства
        mirror_dict = dict(mirror) if hasattr(mirror, 'keys') else mirror
        channel_link = mirror_dict.get("channel_link")
        channel_username = mirror_dict.get("channel_username")
        
        if channel_link and channel_username:
            try:
                member = await bot.get_chat_member(f"@{channel_username}", message.from_user.id)
                is_subscribed = member.status in ("member", "administrator", "creator")
                if not is_subscribed:
                    should_subscribe = True
            except Exception:
                should_subscribe = True
    
    if should_subscribe and channel_link:
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=channel_link)],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_mirror_subscription")],
        ])
        await message.answer(
            "📢 Для использования бота необходима подписка на канал зеркала!\n\n"
            f"🔗 {channel_link}\n\n"
            "После подписки нажмите кнопку ниже:",
            reply_markup=markup
        )
        return
    
    welcome_text = mirror["greeting_text"] if (mirror and mirror["greeting_text"]) else texts.WELCOME
    await message.answer(welcome_text, reply_markup=ReplyKeyboardRemove())
    
    # Проверяем, является ли пользователь создателем зеркала
    user_mirrors = await db.get_mirrors_by_owner(message.from_user.id)
    if user_mirrors:
        await message.answer(
            f"🪞 **Вы создатель зеркала!**\n\n"
            f"Используйте команду /mirrors для управления своими зеркалами."
        )
    
    markup = await keyboards.main_menu(db)
    await send_menu(message, db, texts.MENU, markup)


@router.callback_query(F.data == "check_mirror_subscription")
async def check_mirror_subscription(cb: CallbackQuery, db: Database, bot: Bot, mirror: dict | None = None):
    if not mirror:
        await cb.answer("❌ Канал подписки не настроен.", show_alert=True)
        return
    
    # Преобразуем Row в dict если нужно
    mirror_dict = dict(mirror) if hasattr(mirror, 'keys') else mirror
    channel_username = mirror_dict.get("channel_username")
    
    if not channel_username:
        await cb.answer("❌ Канал подписки не настроен.", show_alert=True)
        return
    
    try:
        member = await bot.get_chat_member(f"@{channel_username}", cb.from_user.id)
        is_subscribed = member.status in ("member", "administrator", "creator")
    except Exception:
        is_subscribed = False
    
    if is_subscribed:
        await cb.message.delete()
        await cb.message.answer(texts.WELCOME, reply_markup=ReplyKeyboardRemove())
        markup = await keyboards.main_menu(db)
        await send_menu(cb.message, db, texts.MENU, markup)
        await cb.answer("✅ Спасибо за подписку!", show_alert=False)
    else:
        await cb.answer("❌ Вы ещё не подписались на канал. Подпишитесь и попробуйте ещё раз.", show_alert=True)


@router.callback_query(F.data == "menu:main")
async def menu_main(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    markup = await keyboards.main_menu(db)
    await send_menu(cb.message, db, texts.MENU, markup)
    await cb.answer()


@router.callback_query(F.data == "menu:more")
async def menu_more(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    markup = await keyboards.more_menu(db)
    await cb.message.answer("⚙️ **Дополнительное меню:**", reply_markup=markup, parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "menu:support")
async def support(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    # Читаем ссылку — сначала новый ключ, потом старый для совместимости
    link = await db.get_setting("link:support_url") or await db.get_setting("link:support")
    markup_rows = []
    if link:
        markup_rows.append([InlineKeyboardButton(text="💬 Написать в поддержку", url=link)])
    markup_rows.append([InlineKeyboardButton(text="ℹ️ О магазине", callback_data="menu:about")])
    markup_rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:main")])
    markup = InlineKeyboardMarkup(inline_keyboard=markup_rows)
    await cb.message.answer(texts.SUPPORT_INFO, reply_markup=markup, parse_mode="Markdown")
    await cb.answer()



@router.callback_query(F.data == "menu:about")
async def menu_about(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    full_text = texts.ABOUT_PROJECT
    # Добавляем каналы, если они заданы
    val = await db.get_setting("about:channels") or ""
    channels = [c for c in val.split(",") if c.strip()]
    if channels:
        ch_lines = ["\n\n🔗 Наши каналы:"]
        ch_buttons = []
        for ch in channels:
            ch_lines.append(f"• @{ch}")
            ch_buttons.append([InlineKeyboardButton(text=f"@{ch}", url=f"https://t.me/{ch}")])
        full_text += "\n" + "\n".join(ch_lines)
    full_text += "\n\n━━━━━━━━━━━━━━━━━━━━━━━\n" + texts.FAQ_TEXT

    # Кнопки: каналы (если есть), поддержка, назад
    markup_rows = []
    if channels:
        markup_rows.extend(ch_buttons)
    markup_rows.append([InlineKeyboardButton(text="💬 Поддержка", callback_data="menu:support")])
    markup_rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:main")])
    markup = InlineKeyboardMarkup(inline_keyboard=markup_rows)
    await cb.message.answer(full_text, reply_markup=markup, parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "menu:catalog")
async def catalog(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    cats = await db.list_categories()
    if not cats:
        await send_tab(cb.message, db, "video:tab:catalog", "🛍️ Каталог пока пуст.", menu_only_kb(), banner_suffix="catalog")
    else:
        rows = [[InlineKeyboardButton(text=c["name"], callback_data=f"cat:{c['id']}:0")] for c in cats]
        rows.append(keyboards.menu_row())
        await send_tab(cb.message, db, "video:tab:catalog", "🛍️ Выберите раздел:",
                       InlineKeyboardMarkup(inline_keyboard=rows), banner_suffix="catalog")
    await cb.answer()


@router.callback_query(F.data.startswith("cat:"))
async def open_category(cb: CallbackQuery, db: Database):
    parts = cb.data.split(":")
    cat_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    
    cat = await db.get_category(cat_id)
    if not cat:
        return await cb.answer("Раздел не найден", show_alert=True)
    
    prods = await db.list_products(cat_id)
    total_items = len(prods)
    total_pages = (total_items + keyboards.ITEMS_PER_PAGE - 1) // keyboards.ITEMS_PER_PAGE
    
    if total_pages == 0:
        total_pages = 1
    
    # Убеждаемся, что страница в диапазоне
    if page >= total_pages:
        page = total_pages - 1
    if page < 0:
        page = 0
    
    # Вычисляем диапазон товаров для текущей страницы
    start_idx = page * keyboards.ITEMS_PER_PAGE
    end_idx = start_idx + keyboards.ITEMS_PER_PAGE
    page_prods = prods[start_idx:end_idx]
    
    rows = []
    for p in page_prods:
        stock = "∞" if p["kind"] == "reusable" else str(await db.stock(p["id"]))
        rows.append([InlineKeyboardButton(
            text=f"{p['name']} — {texts.fmt_usd(p['price'])} [{stock}]",
            callback_data=f"prod:{p['id']}")])
    
    # Пагинация
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"cat:{cat_id}:{page - 1}"))
        else:
            pagination_buttons.append(InlineKeyboardButton(text="◀️", callback_data="noop"))
        
        pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
        
        if page < total_pages - 1:
            pagination_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"cat:{cat_id}:{page + 1}"))
        else:
            pagination_buttons.append(InlineKeyboardButton(text="▶️", callback_data="noop"))
        
        rows.append(pagination_buttons)
    
    rows.append([InlineKeyboardButton(text="⬅️ Каталог", callback_data="menu:catalog")])
    rows.append(keyboards.menu_row())
    
    text = f"📁 {cat['name']}\n\nВыберите товар:" if prods else f"📁 {cat['name']}\n\nЗдесь пока нет товаров."
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if cat["video_file_id"]:
        try:
            await send_media(cb.message, cat["video_file_id"], text, markup)
        except Exception:
            await cb.message.answer(text, reply_markup=markup)
    else:
        await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data.startswith("prod:"))
async def product_card(cb: CallbackQuery, db: Database):
    product_id = int(cb.data.split(":")[1])
    p = await db.get_product(product_id)
    if not p or not p["visible"]:
        return await cb.answer("Товар не найден", show_alert=True)
    stock = "∞" if p["kind"] == "reusable" else f"{await db.stock(product_id)} шт."
    
    # Проверяем, купил ли пользователь этот товар раньше
    purchases = await db.list_purchases(cb.from_user.id, limit=100)
    purchased_this = [pur for pur in purchases if pur["product_id"] == product_id]
    
    text = (f"📦 {p['name']}\n\n{p['description']}\n\n"
            f"💵 Цена: {texts.fmt_usd(p['price'])}\n📦 В наличии: {stock}")
    
    # Информация о покупке
    if purchased_this:
        last_purchase = purchased_this[0]
        text += f"\n\n✅ Вы уже купили этот товар\n"
        text += f"📅 Дата покупки: {last_purchase['created_at'][:16]}\n"
        text += f"💵 Цена была: {texts.fmt_usd(last_purchase['price'])}"
    
    # Кнопка действия
    buttons = []
    if p["price"] == 0:
        buy_btn = InlineKeyboardButton(text="🎁 Получить бесплатно", callback_data=f"buynow:{p['id']}")
    else:
        buy_btn = InlineKeyboardButton(
            text=f"💰 Купить за {texts.fmt_usd(p['price'])}", callback_data=f"buynow:{p['id']}")
    
    buttons.append([buy_btn])
    
    # Если уже купил - добавляем кнопку "Получить снова" для одноразовых товаров
    if purchased_this and p["kind"] == "oneoff":
        buttons.append([InlineKeyboardButton(text="🔄 Получить снова из истории", 
                                           callback_data=f"again:{purchased_this[0]['id']}")])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat:{p['category_id']}")])
    buttons.append(keyboards.menu_row())
    
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    photos = await db.list_product_photos(product_id)
    file_ids = [ph["file_id"] for ph in photos]
    try:
        await send_product_photos(cb.message, file_ids, text, markup)
    except Exception:
        await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data == "menu:profile")
async def profile(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    user = await db.get_or_create_user(cb.from_user.id, cb.from_user.username)
    count = await db.count_purchases(cb.from_user.id)
    currency = user['currency'] if user and 'currency' in user.keys() else 'USD'
    text = (f"👤 Профиль\n\n🆔 ID: {cb.from_user.id}\n"
            f"💰 Баланс: {texts.fmt_balance(user['balance'], currency)}\n🛒 Покупок: {count}")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💱 Валюта: {currency}", callback_data="profile:currency")],
        [InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup")],
        keyboards.menu_row(),
    ])
    await send_tab(cb.message, db, "video:tab:profile", text, markup, banner_suffix="profile")
    await cb.answer()


@router.callback_query(F.data == "menu:history")
async def history(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    purchases = await db.list_purchases(cb.from_user.id, limit=10)
    if not purchases:
        await send_tab(cb.message, db, "video:tab:history", "📜 У вас пока нет покупок.", menu_only_kb(), banner_suffix="history")
        return await cb.answer()
    
    lines = ["📜 Ваши покупки:", ""]
    rows = []
    for p in purchases:
        lines.append(f"📦 {p['product_name']}")
        lines.append(f"   💵 Цена: {texts.fmt_usd(p['price'])}")
        lines.append(f"   📅 Дата: {p['created_at'][:16]}")
        lines.append("")
        rows.append([InlineKeyboardButton(text=f"🔄 {p['product_name']}", callback_data=f"again:{p['id']}")])
    
    rows.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="menu:main")])
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
    currency = user['currency'] if user and 'currency' in user.keys() else 'USD'
    text = texts.REFERRAL.format(link=link, invited=invited,
                                 percent=percent_for_clients(clients),
                                 earned=texts.fmt_balance(earned, currency))
    await send_tab(cb.message, db, "video:tab:referral", text, menu_only_kb(), banner_suffix="referral")
    await cb.answer()


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
    currency = user['currency'] if user and 'currency' in user.keys() else 'USD'
    text = (f"👤 Профиль\n\n🆔 ID: {cb.from_user.id}\n"
            f"💰 Баланс: {texts.fmt_balance(user['balance'], currency)}\n🛒 Покупок: {count}")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💱 Валюта: {currency}", callback_data="profile:currency")],
        [InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="topup")],
        keyboards.menu_row(),
    ])
    await cb.message.answer(text, reply_markup=markup)


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
async def about_project(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    markup = InlineKeyboardMarkup(inline_keyboard=[
       [InlineKeyboardButton(text="📚 FAQ", callback_data="about:faq")],
       [InlineKeyboardButton(text="📺 Реклама", url="https://t.me/glock_price")],
       [InlineKeyboardButton(text="📰 Новостной канал", url="https://t.me/news_glock_shop")],
       [InlineKeyboardButton(text="⭐ Отзывы", url="https://t.me/reps_glock_shop")],
       keyboards.menu_row(),
    ])
    await cb.message.answer(texts.ABOUT_PROJECT, reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data == "about:faq")
async def about_faq(cb: CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[
       [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:about")],
       keyboards.menu_row(),
    ])
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


# ===== АДМИНКА =====

@router.message(F.text == "/admin")
async def cmd_admin(message: Message, db: Database, config, state: FSMContext):
    """Команда /admin - перенаправляет в админку основного админа или в админку зеркала"""
    # Проверяем, является ли пользователь основным админом
    if message.from_user.username and config.admin_username and \
       message.from_user.username.lower() == config.admin_username.lower():
        # Основной админ - показываем его админку
        await state.clear()
        from handlers.admin import admin_menu_kb
        await message.answer("⚙️ Админ-панель", reply_markup=admin_menu_kb())
        return
    
    # Проверяем, является ли пользователь создателем зеркала
    user_mirrors = await db.get_mirrors_by_owner(message.from_user.id)
    if user_mirrors:
        # Создатель зеркала - показываем его админку
        from handlers.mirror_admin import cmd_mirrors
        await cmd_mirrors(message, db)
    else:
        await message.answer("❌ У вас нет доступа к админке.")


@router.message(F.text == "/mirrors")
async def cmd_mirrors_msg(message: Message, db: Database):
    """Команда /mirrors - админка для создателей зеркал"""
    from handlers.mirror_admin import cmd_mirrors
    await cmd_mirrors(message, db)
