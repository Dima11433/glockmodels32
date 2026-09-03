from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

import texts
from config import Config
from db import Database
from media import MAX_PHOTOS, media_of, photo_file_id
from photo_manager import download_and_save_photo
from aiogram import Bot

router = Router()


class AdminFilter(BaseFilter):
    async def __call__(self, event: TelegramObject, config: Config, db: Database) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False
        # Check legacy single admin from config
        if user.username and config.admin_username and user.username.lower() == config.admin_username.lower():
            return True
        # Check database admins by user_id or username
        try:
            if await db.is_admin(user.id, user.username):
                return True
        except Exception:
            # If DB not available for some reason, deny access
            return False
        return False


router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

TAB_VIDEOS = []  # Видео вкладки удалены

LINKS = [("support", "💬 Поддержка")]

BUTTONS = [
    ("search", "🔍 Поиск"),
    ("catalog", "🛍️ Каталог"),
    ("profile", "👤 Профиль"),
    ("history", "📜 История"),
    ("referral", "🤝 Рефералка"),
    ("support", "💬 Поддержка"),
]


class ButtonEdit(StatesGroup):
    value = State()


class DescriptionEdit(StatesGroup):
    value = State()


class BannerUpload(StatesGroup):
    photo = State()


class CatAdd(StatesGroup):
    name = State()
    description = State()
    video = State()


class SubCatAdd(StatesGroup):
    name = State()
    description = State()
    video = State()


class CatRename(StatesGroup):
    name = State()


class CatDesc(StatesGroup):
    description = State()


class CatVideo(StatesGroup):
    video = State()


class LinkEdit(StatesGroup):
    url = State()


class UserSearch(StatesGroup):
    query = State()


class MailingMessage(StatesGroup):
    text = State()


class AddBalance(StatesGroup):
    user_id = State()
    amount = State()


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Админы", callback_data="adm:admins"),
         InlineKeyboardButton(text="📁 Разделы", callback_data="adm:cats")],
        [InlineKeyboardButton(text="📦 Товары", callback_data="adm:prods"),
         InlineKeyboardButton(text="📢 Автопостинг", callback_data="adm:autopost")],
        [InlineKeyboardButton(text="🏷 Скидки & Наценки (%)", callback_data="adm:pricing")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users"),
         InlineKeyboardButton(text="📋 Логи", callback_data="adm:logs")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="adm:mailing"),
         InlineKeyboardButton(text="🌴 Реклама & Брони", callback_data="adm:ads")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
         InlineKeyboardButton(text="💳 Выплаты Зеркал", callback_data="adm:withdrawals")],
        [InlineKeyboardButton(text="🎫 Создать Промокод", callback_data="adm:create_promo"),
         InlineKeyboardButton(text="🔗 Ссылки", callback_data="adm:links")],
        [InlineKeyboardButton(text="🎨 Дизайн кнопок", callback_data="adm:btns"),
         InlineKeyboardButton(text="ℹ️ О Магазине", callback_data="adm:about_channels")],
        [InlineKeyboardButton(text="📣 Обяз.подп.", callback_data="adm:req_channels")],
    ])


@router.message(Command("admin"))
async def admin_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("⚙️ Админ-панель", reply_markup=admin_menu_kb())


class AdminManage(StatesGroup):
    add_username = State()
    set_role = State()


@router.callback_query(F.data == "adm:admins")
async def adm_admins(cb: CallbackQuery, db: Database):
    admins = await db.list_admins()
    lines = ["👑 Админы:"]
    rows = []
    for a in admins:
        name = a["username"] or (str(a["user_id"]) if a["user_id"] else f"(id:{a['id']})")
        lines.append(f"{name} — {a['role']}")
        rows.append([
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:admin_del:{a['id']}"),
            InlineKeyboardButton(text="✏️ Роль", callback_data=f"adm:admin_role:{a['id']}")
        ])
    rows.append([InlineKeyboardButton(text="➕ Добавить админа", callback_data="adm:add_admin")])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    await cb.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data == "adm:add_admin")
async def adm_add_admin(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminManage.add_username)
    await cb.message.answer("Введите username (с @ или без) или numeric id пользователя, которого сделать админом:")
    await cb.answer()


@router.message(AdminManage.add_username, F.text)
async def adm_add_admin_done(message: Message, db: Database, state: FSMContext):
    text = message.text.strip()
    user_id = None
    username = None
    if text.isdigit():
        user_id = int(text)
    else:
        username = text.lstrip("@")
    await db.add_admin(user_id, username, 'product')
    await state.clear()
    await message.answer("✅ Админ добавлен.", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("adm:admin_del:"))
async def adm_admin_del(cb: CallbackQuery, db: Database):
    aid = int(cb.data.split(":")[2])
    await db.remove_admin_by_id(aid)
    await cb.answer("Удалён ✅")


@router.callback_query(F.data.startswith("adm:admin_role:"))
async def adm_admin_role(cb: CallbackQuery, db: Database, state: FSMContext):
    aid = int(cb.data.split(":")[2])
    await state.set_state(AdminManage.set_role)
    await state.update_data(admin_id=aid)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Суперадмин (полные права)", callback_data="adm:role_choice:super")],
        [InlineKeyboardButton(text="📦 Товары", callback_data="adm:role_choice:product")],
        [InlineKeyboardButton(text="📁 Разделы", callback_data="adm:role_choice:category")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="adm:role_choice:mailing")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="adm:admins")],
    ])
    await cb.message.answer("Выберите роль для админа:", reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:role_choice:"))
async def adm_role_choice(cb: CallbackQuery, db: Database, state: FSMContext):
    role = cb.data.split(":")[2]
    data = await state.get_data()
    admin_id = data.get("admin_id")
    if not admin_id:
        return await cb.answer("Что-то пошло не так", show_alert=True)
    await db.set_admin_role_by_id(admin_id, role)
    await state.clear()
    await cb.message.answer("✅ Роль обновлена.", reply_markup=admin_menu_kb())
    await cb.answer()


# --- каналы покупки ---

class ChannelManage(StatesGroup):
    add_channel = State()


@router.callback_query(F.data == "adm:channels")
async def adm_channels(cb: CallbackQuery, db: Database):
    channels = await db.list_purchase_channels()
    lines = ["📣 Каналы для обязательной подписки перед покупкой:"]
    rows = []
    if channels:
        for ch in channels:
            uname = ch["username"]
            title = ch["title"] or ""
            lines.append(f"@{uname} {('- '+title) if title else ''}")
            rows.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:channel_del:{ch['id']}")])
    else:
        lines.append("(пока не добавлено)")
    rows.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="adm:add_channel")])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    await cb.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data == "adm:add_channel")
async def adm_add_channel(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ChannelManage.add_channel)
    await cb.message.answer("Пришлите username канала (с @ или без) или ссылку на канал (https://t.me/...) :")
    await cb.answer()


@router.message(ChannelManage.add_channel, F.text)
async def adm_add_channel_done(message: Message, db: Database, state: FSMContext):
    text = message.text.strip()
    if text.startswith("https://t.me/"):
        uname = text.split("t.me/")[1].strip('/')
    else:
        uname = text.lstrip('@')
    await db.add_purchase_channel(uname, None)
    await state.clear()
    await message.answer("✅ Канал добавлен.", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("adm:channel_del:"))
async def adm_channel_del(cb: CallbackQuery, db: Database):
    cid = int(cb.data.split(":")[2])
    await db.remove_purchase_channel(cid)
    await cb.answer("Удалён ✅")


# --- обязательные каналы для использования бота ---

class ReqChannelManage(StatesGroup):
    add_channel = State()


@router.callback_query(F.data == "adm:req_channels")
async def adm_req_channels(cb: CallbackQuery, db: Database):
    channels = await db.list_required_channels()
    lines = ["📣 Обязательная подписка (для использования бота):"]
    rows = []
    if channels:
        for ch in channels:
            uname = ch["username"]
            title = ch["title"] or ""
            lines.append(f"@{uname} {('- '+title) if title else ''}")
            rows.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:req_channel_del:{ch['id']}")])
    else:
        lines.append("(пока не добавлено)")
    rows.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="adm:add_req_channel")])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    await cb.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data == "adm:add_req_channel")
async def adm_add_req_channel(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ReqChannelManage.add_channel)
    await cb.message.answer("Пришлите username канала (с @ или без) или ссылку на канал (https://t.me/...) :")
    await cb.answer()


@router.message(ReqChannelManage.add_channel, F.text)
async def adm_add_req_channel_done(message: Message, db: Database, state: FSMContext):
    text = message.text.strip()
    if text.startswith("https://t.me/"):
        uname = text.split("t.me/")[1].strip('/')
    else:
        uname = text.lstrip('@')
    await db.add_required_channel(uname, None)
    await state.clear()
    await message.answer("✅ Канал добавлен.", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("adm:req_channel_del:"))
async def adm_req_channel_del(cb: CallbackQuery, db: Database):
    cid = int(cb.data.split(":")[2])
    await db.remove_required_channel(cid)
    await cb.answer("Удалён ✅")


# --- О Магазине / О проекте (админка) ---
class AboutChannelManage(StatesGroup):
    add_channel = State()


@router.callback_query(F.data == "adm:about_channels")
async def adm_about_channels(cb: CallbackQuery, db: Database):
    channels = await db.list_about_channels()
    lines = ["ℹ️ <b>Раздел «О Магазине / О проекте»:</b>\n"]
    rows = []
    if channels:
        for ch in channels:
            cid = ch["id"] if "id" in ch.keys() else ch[0]
            uname = ch["username"] or ""
            title = ch["title"] or ""
            url = ch["url"] or (f"https://t.me/{uname}" if uname else None)
            label = title or (f"@{uname}" if uname else (url or "Ссылка"))
            lines.append(f"• <b>{label}</b>\n  └ {url or uname}")
            
            btns = [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:about_channel_del:{cid}")
            ]
            if url:
                btns.append(InlineKeyboardButton(text="🔗 Открыть", url=url))
            rows.append(btns)
    else:
        lines.append("<i>(Каналы пока не добавлены)</i>")

    rows.append([InlineKeyboardButton(text="➕ Добавить канал / проект", callback_data="adm:add_about_channel")])
    rows.append([InlineKeyboardButton(text="⬅️ Админ-меню", callback_data="adm:menu")])

    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await cb.message.edit_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")
    except Exception:
        await cb.message.answer("\n".join(lines), reply_markup=markup, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:add_about_channel")
async def adm_add_about_channel(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AboutChannelManage.add_channel)
    text = (
        "➕ <b>Добавление канала / проекта</b>\n\n"
        "Отправьте username или ссылку. Также можно указать название через <code>|</code>:\n\n"
        "<b>Примеры:</b>\n"
        "• <code>@news_channel | 📰 Новости магазина</code>\n"
        "• <code>https://t.me/our_projects | ❇️ Наши проекты</code>\n"
        "• <code>https://t.me/reps_channel | ⭐ Отзывы</code>\n"
        "• <code>@glock_price</code>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:about_channels")]
    ])
    await cb.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()


@router.message(AboutChannelManage.add_channel, F.text)
async def adm_add_about_channel_done(message: Message, db: Database, state: FSMContext):
    raw = message.text.strip()
    parts = [p.strip() for p in raw.split("|", 1)]
    
    # Определяем где ссылка, а где название
    if len(parts) == 2:
        p0, p1 = parts[0], parts[1]
        if p0.startswith("http://") or p0.startswith("https://") or p0.startswith("@") or "t.me/" in p0:
            identifier, title = p0, p1
        else:
            title, identifier = p0, p1
    else:
        identifier = parts[0]
        title = None

    username = None
    url = None
    if identifier.startswith("http://") or identifier.startswith("https://"):
        url = identifier
        if "t.me/" in identifier:
            username = identifier.split("t.me/")[1].strip("/").split("/")[0]
    elif identifier.startswith("@") or ("_" in identifier or identifier.isalnum()):
        username = identifier.lstrip("@")
        url = f"https://t.me/{username}"
    else:
        url = identifier

    if not title:
        title = f"@{username}" if username else url

    await db.add_about_channel(username=username, title=title, url=url)
    await state.clear()

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ℹ️ К списку каналов", callback_data="adm:about_channels")],
        [InlineKeyboardButton(text="⬅️ Админ-меню", callback_data="adm:menu")]
    ])
    await message.answer(f"✅ Канал/проект <b>{title}</b> успешно добавлен!\nСсылка: <code>{url}</code>", reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm:about_channel_del:"))
async def adm_about_channel_del(cb: CallbackQuery, db: Database):
    cid = int(cb.data.split(":")[2])
    await db.remove_about_channel(cid)
    await cb.answer("Удалено ✅")
    await adm_about_channels(cb, db)


@router.callback_query(F.data == "adm:menu")
async def adm_menu_cb(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("⚙️ Админ-панель", reply_markup=admin_menu_kb())
    await cb.answer()


# --- разделы и подкатегории ---

@router.callback_query(F.data == "adm:cats")
async def adm_cats(cb: CallbackQuery, db: Database):
    cats = await db.list_categories(parent_id=None)
    rows = []
    for c in cats:
        sub_n = await db.count_subcategories(c["id"])
        prod_n = await db.count_products(c["id"])
        info = []
        if sub_n:
            info.append(f"📂 {sub_n}")
        if prod_n:
            info.append(f"📦 {prod_n}")
        info_str = f" ({', '.join(info)})" if info else ""
        rows.append([InlineKeyboardButton(text=f"📁 {c['name']}{info_str}", callback_data=f"adm:cat:{c['id']}")])
    rows.append([InlineKeyboardButton(text="➕ Создать главный раздел", callback_data="adm:add_cat")])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    await cb.message.answer("📁 <b>Управление разделами каталога:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:cat:"))
async def adm_cat(cb: CallbackQuery, db: Database):
    cat_id = int(cb.data.split(":")[2])
    cat = await db.get_category(cat_id)
    if not cat:
        return await cb.answer("Раздел не найден", show_alert=True)
    
    subcats = await db.list_subcategories(cat_id)
    prods_count = await db.count_products(cat_id)
    video = "есть ✅" if ("video_file_id" in cat.keys() and cat["video_file_id"]) else "нет"
    desc = cat["description"] if ("description" in cat.keys() and cat["description"]) else ""
    desc_display = f"\n📝 Описание: <b>{desc}</b>" if desc else "\n📝 Описание: <i>(не задано)</i>"

    title_chain = f"📁 {cat['name']}"
    back_target = "adm:cats"
    if "parent_id" in cat.keys() and cat["parent_id"]:
        parent = await db.get_category(cat["parent_id"])
        if parent:
            title_chain = f"📁 {parent['name']} ➔ 📂 {cat['name']}"
            back_target = f"adm:cat:{cat['parent_id']}"

    rows = [
        [InlineKeyboardButton(text=f"➕ Создать подраздел внутри", callback_data=f"adm:add_subcat:{cat_id}")],
    ]
    if subcats:
        rows.append([InlineKeyboardButton(text=f"📂 Подразделы ({len(subcats)})", callback_data=f"adm:subcats:{cat_id}")])
    
    rows.append([
        InlineKeyboardButton(text=f"📦 Товары раздела ({prods_count})", callback_data=f"adm:pcat:{cat_id}"),
        InlineKeyboardButton(text="➕ Добавить товар", callback_data=f"adm:add_prod:{cat_id}")
    ])
    rows.append([
        InlineKeyboardButton(text="✏️ Название", callback_data=f"adm:cat_rename:{cat_id}"),
        InlineKeyboardButton(text="✏️ Описание", callback_data=f"adm:cat_desc:{cat_id}")
    ])
    rows.append([
        InlineKeyboardButton(text="🎬 Видео/баннер", callback_data=f"adm:cat_video:{cat_id}"),
        InlineKeyboardButton(text="🗑 Удалить видео", callback_data=f"adm:cat_video_del:{cat_id}")
    ])
    rows.append([InlineKeyboardButton(text="❌ Удалить этот раздел", callback_data=f"adm:cat_del:{cat_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_target)])

    text = (
        f"<b>{title_chain}</b>\n"
        f"{desc_display}\n\n"
        f"📂 Вложенных подразделов: <b>{len(subcats)}</b>\n"
        f"📦 Товаров в этом разделе: <b>{prods_count}</b>\n"
        f"🎬 Видео/баннер: <b>{video}</b>"
    )
    await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:subcats:"))
async def adm_subcats(cb: CallbackQuery, db: Database):
    parent_id = int(cb.data.split(":")[2])
    parent = await db.get_category(parent_id)
    if not parent:
        return await cb.answer("Раздел не найден", show_alert=True)
    
    subcats = await db.list_subcategories(parent_id)
    rows = []
    for sc in subcats:
        sc_sub_n = await db.count_subcategories(sc["id"])
        sc_prod_n = await db.count_products(sc["id"])
        info = []
        if sc_sub_n:
            info.append(f"📂 {sc_sub_n}")
        if sc_prod_n:
            info.append(f"📦 {sc_prod_n}")
        info_str = f" ({', '.join(info)})" if info else ""
        rows.append([InlineKeyboardButton(text=f"📂 {sc['name']}{info_str}", callback_data=f"adm:cat:{sc['id']}")])
    
    rows.append([InlineKeyboardButton(text="➕ Создать подраздел", callback_data=f"adm:add_subcat:{parent_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в раздел", callback_data=f"adm:cat:{parent_id}")])
    
    await cb.message.answer(
        f"📂 <b>Подразделы внутри «{parent['name']}»:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data == "adm:add_cat")
async def adm_add_cat(cb: CallbackQuery, state: FSMContext):
    await state.set_state(CatAdd.name)
    await cb.message.answer("Введите название главного раздела:")
    await cb.answer()


@router.message(CatAdd.name, F.text)
async def adm_add_cat_name(message: Message, db: Database, state: FSMContext):
    name = message.text.strip()
    if not name:
        return await message.answer("Название не может быть пустым. Введите ещё раз:")
    await state.update_data(cat_name=name)
    await state.set_state(CatAdd.description)
    await message.answer("📝 Введите описание раздела (или отправьте /skip, чтобы пропустить):")


@router.message(CatAdd.description, Command("skip"))
async def adm_add_cat_desc_skip(message: Message, db: Database, state: FSMContext):
    data = await state.get_data()
    cat_id = await db.add_category(data["cat_name"], parent_id=None, description="")
    await state.update_data(cat_id=cat_id)
    await state.set_state(CatAdd.video)
    await message.answer("Пришлите видео/GIF для раздела (до 5 секунд) или отправьте /skip:")


@router.message(CatAdd.description, F.text)
async def adm_add_cat_desc(message: Message, db: Database, state: FSMContext):
    desc = message.text.strip()
    data = await state.get_data()
    cat_id = await db.add_category(data["cat_name"], parent_id=None, description=desc)
    await state.update_data(cat_id=cat_id)
    await state.set_state(CatAdd.video)
    await message.answer("Пришлите видео/GIF для раздела (до 5 секунд) или отправьте /skip:")


@router.message(CatAdd.video, Command("skip"))
async def adm_add_cat_skip(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Главный раздел создан.", reply_markup=admin_menu_kb())


@router.message(CatAdd.video)
async def adm_add_cat_video(message: Message, db: Database, state: FSMContext):
    media = media_of(message)
    if not media:
        return await message.answer("Это не медиа. Пришлите видео/GIF или /skip:")
    data = await state.get_data()
    await db.set_category_video(data["cat_id"], media)
    await state.clear()
    await message.answer("✅ Главный раздел создан с видео.", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("adm:add_subcat:"))
async def adm_add_subcat(cb: CallbackQuery, state: FSMContext, db: Database):
    parent_id = int(cb.data.split(":")[2])
    parent = await db.get_category(parent_id)
    parent_name = parent["name"] if parent else "раздела"
    await state.set_state(SubCatAdd.name)
    await state.update_data(parent_id=parent_id)
    await cb.message.answer(f"Введите название нового подраздела внутри «<b>{parent_name}</b>»:", parse_mode="HTML")
    await cb.answer()


@router.message(SubCatAdd.name, F.text)
async def adm_add_subcat_name(message: Message, db: Database, state: FSMContext):
    name = message.text.strip()
    if not name:
        return await message.answer("Название не может быть пустым. Введите ещё раз:")
    await state.update_data(subcat_name=name)
    await state.set_state(SubCatAdd.description)
    await message.answer("📝 Введите описание подраздела (или отправьте /skip, чтобы пропустить):")


@router.message(SubCatAdd.description, Command("skip"))
async def adm_add_subcat_desc_skip(message: Message, db: Database, state: FSMContext):
    data = await state.get_data()
    parent_id = data.get("parent_id")
    cat_id = await db.add_category(data["subcat_name"], parent_id=parent_id, description="")
    await state.update_data(cat_id=cat_id, parent_id=parent_id)
    await state.set_state(SubCatAdd.video)
    await message.answer("Пришлите видео/GIF для подраздела (до 5 секунд) или отправьте /skip:")


@router.message(SubCatAdd.description, F.text)
async def adm_add_subcat_desc(message: Message, db: Database, state: FSMContext):
    desc = message.text.strip()
    data = await state.get_data()
    parent_id = data.get("parent_id")
    cat_id = await db.add_category(data["subcat_name"], parent_id=parent_id, description=desc)
    await state.update_data(cat_id=cat_id, parent_id=parent_id)
    await state.set_state(SubCatAdd.video)
    await message.answer("Пришлите видео/GIF для подраздела (до 5 секунд) или отправьте /skip:")


@router.message(SubCatAdd.video, Command("skip"))
async def adm_add_subcat_skip(message: Message, state: FSMContext):
    data = await state.get_data()
    parent_id = data.get("parent_id")
    await state.clear()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 К разделу", callback_data=f"adm:cat:{parent_id}")]
    ]) if parent_id else admin_menu_kb()
    await message.answer("✅ Подраздел успешно создан!", reply_markup=markup)


@router.message(SubCatAdd.video)
async def adm_add_subcat_video(message: Message, db: Database, state: FSMContext):
    media = media_of(message)
    if not media:
        return await message.answer("Это не медиа. Пришлите видео/GIF или /skip:")
    data = await state.get_data()
    await db.set_category_video(data["cat_id"], media)
    parent_id = data.get("parent_id")
    await state.clear()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 К разделу", callback_data=f"adm:cat:{parent_id}")]
    ]) if parent_id else admin_menu_kb()
    await message.answer("✅ Подраздел успешно создан с видео!", reply_markup=markup)


@router.callback_query(F.data.startswith("adm:cat_rename:"))
async def adm_cat_rename(cb: CallbackQuery, state: FSMContext):
    await state.set_state(CatRename.name)
    await state.update_data(cat_id=int(cb.data.split(":")[2]))
    await cb.message.answer("Введите новое название раздела:")
    await cb.answer()


@router.message(CatRename.name, F.text)
async def adm_cat_rename_done(message: Message, db: Database, state: FSMContext):
    data = await state.get_data()
    cat_id = data["cat_id"]
    await db.rename_category(cat_id, message.text.strip())
    await state.clear()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 К разделу", callback_data=f"adm:cat:{cat_id}")]
    ])
    await message.answer("✅ Переименовано.", reply_markup=markup)


@router.callback_query(F.data.startswith("adm:cat_desc:"))
async def adm_cat_desc(cb: CallbackQuery, state: FSMContext):
    await state.set_state(CatDesc.description)
    await state.update_data(cat_id=int(cb.data.split(":")[2]))
    await cb.message.answer(
        "📝 Введите новое описание для раздела.\n"
        "Чтобы очистить/удалить описание, отправьте <code>clear</code> или <code>/remove</code>:",
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(CatDesc.description, F.text)
async def adm_cat_desc_done(message: Message, db: Database, state: FSMContext):
    data = await state.get_data()
    cat_id = data["cat_id"]
    text = message.text.strip()
    if text.lower() in ("clear", "/remove", "удалить", "/skip", "-"):
        text = ""
    await db.set_category_description(cat_id, text)
    await state.clear()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 К разделу", callback_data=f"adm:cat:{cat_id}")]
    ])
    if text:
        await message.answer(f"✅ Описание раздела сохранено:\n\n{text}", reply_markup=markup)
    else:
        await message.answer("✅ Описание раздела удалено.", reply_markup=markup)


@router.callback_query(F.data.startswith("adm:cat_video_del:"))
async def adm_cat_video_del(cb: CallbackQuery, db: Database):
    cat_id = int(cb.data.split(":")[2])
    await db.set_category_video(cat_id, None)
    await cb.answer("Видео удалено ✅")
    await adm_cat(cb, db)


@router.callback_query(F.data.startswith("adm:cat_video:"))
async def adm_cat_video(cb: CallbackQuery, state: FSMContext):
    await state.set_state(CatVideo.video)
    await state.update_data(cat_id=int(cb.data.split(":")[2]))
    await cb.message.answer("Пришлите видео/GIF для раздела (до 5 секунд):")
    await cb.answer()


@router.message(CatVideo.video)
async def adm_cat_video_done(message: Message, db: Database, state: FSMContext):
    media = media_of(message)
    if not media:
        return await message.answer("Это не медиа. Пришлите видео:")
    data = await state.get_data()
    cat_id = data["cat_id"]
    await db.set_category_video(cat_id, media)
    await state.clear()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 К разделу", callback_data=f"adm:cat:{cat_id}")]
    ])
    await message.answer("✅ Видео обновлено.", reply_markup=markup)


@router.callback_query(F.data.startswith("adm:cat_del_yes:"))
async def adm_cat_del_yes(cb: CallbackQuery, db: Database):
    cat_id = int(cb.data.split(":")[2])
    cat = await db.get_category(cat_id)
    parent_id = cat["parent_id"] if (cat and "parent_id" in cat.keys()) else None
    await db.delete_category(cat_id)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 К разделам", callback_data=f"adm:cat:{parent_id}" if parent_id else "adm:cats")]
    ])
    await cb.message.answer("🗑 Раздел удалён.", reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:cat_del:"))
async def adm_cat_del(cb: CallbackQuery, db: Database):
    cat_id = int(cb.data.split(":")[2])
    n_prods = await db.count_products(cat_id)
    n_sub = await db.count_subcategories(cat_id)
    warns = []
    if n_prods:
        warns.append(f"📦 {n_prods} товар(ов)")
    if n_sub:
        warns.append(f"📂 {n_sub} подраздел(ов)")
    warn_text = f"\n⚠️ Будет удалено: {', '.join(warns)}!" if warns else ""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Да, удалить", callback_data=f"adm:cat_del_yes:{cat_id}")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"adm:cat:{cat_id}")],
    ])
    await cb.message.answer(f"Удалить раздел?{warn_text}", reply_markup=markup)
    await cb.answer()


# --- ссылки ---

@router.callback_query(F.data == "adm:links")
async def adm_links(cb: CallbackQuery, db: Database):
    lines = ["🔗 Ссылки:"]
    rows = []
    for suffix, title in LINKS:
        value = await db.get_setting(f"link:{suffix}") or "не задана"
        lines.append(f"{title}: {value}")
        rows.append([InlineKeyboardButton(text=f"✏️ {title}", callback_data=f"adm:link:{suffix}")])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    await cb.message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:link:"))
async def adm_link(cb: CallbackQuery, state: FSMContext):
    await state.set_state(LinkEdit.url)
    await state.update_data(suffix=cb.data.split(":")[2])
    await cb.message.answer("Пришлите ссылку (https://...):")
    await cb.answer()


@router.message(LinkEdit.url, F.text)
async def adm_link_done(message: Message, db: Database, state: FSMContext):
    url = message.text.strip()
    if not url.startswith(("http://", "https://")):
        return await message.answer("Ссылка должна начинаться с http:// или https://. Пришлите ещё раз:")
    data = await state.get_data()
    await db.set_setting(f"link:{data['suffix']}", url)
    await state.clear()
    await message.answer("✅ Ссылка сохранена.", reply_markup=admin_menu_kb())





@router.callback_query(F.data == "adm:btn_banner")
async def adm_btn_banner(cb: CallbackQuery, state: FSMContext):
    # global banner upload
    await state.set_state(BannerUpload.photo)
    await state.update_data(banner_suffix=None)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить текущий баннер", callback_data="adm:btn_banner_del")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:btns")],
    ])
    await cb.message.answer(
        "🖼 <b>Глобальный баннер меню</b>\n\n"
        "Отправьте <b>фото</b>, <b>GIF-анимацию</b> или <b>видео</b> (или /remove для удаления):",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data == "adm:btn_banner_del")
async def adm_btn_banner_del(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    await db.delete_setting("btn:banner")
    await cb.answer("Глобальный баннер удалён ✅")
    await cb.message.answer("✅ Глобальный баннер удалён.", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("adm:btn_banner:"))
async def adm_btn_banner_for(cb: CallbackQuery, state: FSMContext):
    # per-button banner upload
    suffix = cb.data.split(":")[2]
    await state.set_state(BannerUpload.photo)
    await state.update_data(banner_suffix=suffix)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить баннер", callback_data=f"adm:btn_banner_del:{suffix}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:btns")],
    ])
    await cb.message.answer(
        f"🖼 <b>Баннер для раздела '{suffix}'</b>\n\n"
        f"Отправьте <b>фото</b>, <b>GIF-анимацию</b> или <b>видео</b> (или /remove для удаления):",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:btn_banner_del:"))
async def adm_btn_banner_del_for(cb: CallbackQuery, db: Database, state: FSMContext):
    await state.clear()
    suffix = cb.data.split(":")[2]
    await db.delete_setting(f"btn:banner:{suffix}")
    await cb.answer("Баннер кнопки удалён ✅")
    await cb.message.answer(f"✅ Баннер кнопки '{suffix}' удалён.", reply_markup=admin_menu_kb())


@router.message(BannerUpload.photo)
async def adm_btn_banner_done(message: Message, db: Database, state: FSMContext, bot: Bot):
    if message.text and message.text.strip() == "/remove":
        data = await state.get_data()
        suffix = data.get("banner_suffix")
        if suffix:
            await db.delete_setting(f"btn:banner:{suffix}")
        else:
            await db.delete_setting("btn:banner")
        await state.clear()
        return await message.answer("✅ Баннер удалён.", reply_markup=admin_menu_kb())

    saved = None
    if message.animation:
        saved = f"anim|{message.animation.file_id}"
    elif message.video:
        saved = f"video|{message.video.file_id}"
    elif message.photo:
        file_id = message.photo[-1].file_id
        saved = f"photo|{file_id}"
    else:
        return await message.answer("❌ Пожалуйста, отправьте фото, GIF-анимацию или видео (или /remove).")

    data = await state.get_data()
    suffix = data.get("banner_suffix")
    if suffix:
        await db.set_setting(f"btn:banner:{suffix}", saved)
    else:
        await db.set_setting("btn:banner", saved)

    await state.clear()
    media_type = "GIF-анимация" if "anim|" in saved else ("Видео" if "video|" in saved else "Фото")
    await message.answer(f"✅ Баннер ({media_type}) успешно сохранён!", reply_markup=admin_menu_kb())


# --- товары ---

class ProdAdd(StatesGroup):
    name = State()
    description = State()
    price = State()
    content = State()
    items = State()
    photos = State()


class ProdEdit(StatesGroup):
    value = State()


class ProdStock(StatesGroup):
    stock = State()


class ProdItems(StatesGroup):
    items = State()


class ProdPhotos(StatesGroup):
    photos = State()


def item_of(message: Message) -> tuple[str, str] | None:
    if message.document:
        return ("file", message.document.file_id)
    if message.text:
        return ("text", message.text)
    return None


async def load_items(message: Message, db: Database, product_id: int) -> int:
    if message.document:
        await db.add_items(product_id, [("file", message.document.file_id)])
        return 1
    if message.text:
        lines = [line.strip() for line in message.text.splitlines() if line.strip()]
        if lines:
            await db.add_items(product_id, [("text", line) for line in lines])
        return len(lines)
    return 0


@router.callback_query(F.data == "adm:prods")
async def adm_prods(cb: CallbackQuery, db: Database):
    all_cats = await db.list_all_categories_flat()
    if not all_cats:
        return await cb.answer("Сначала создайте раздел", show_alert=True)
    rows = [
        [InlineKeyboardButton(text="🏷 Скидки & Наценки (%)", callback_data="adm:pricing")]
    ]
    for c in all_cats:
        prod_n = await db.count_products(c["id"])
        count_str = f" ({prod_n} шт)" if prod_n else ""
        rows.append([InlineKeyboardButton(text=f"{c['display_name']}{count_str}", callback_data=f"adm:pcat:{c['id']}")])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    await cb.message.answer("📦 <b>Выберите раздел/подраздел для управления товарами или настройте цены (%):</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:pcat:"))
async def adm_pcat(cb: CallbackQuery, db: Database):
    cat_id = int(cb.data.split(":")[2])
    cat = await db.get_category(cat_id)
    cat_name = cat["name"] if cat else "раздела"
    prods = await db.list_products(cat_id, visible_only=False)
    rows = []
    for p in prods:
        mark = "" if p["visible"] else " 🚫"
        if "old_price" in p.keys() and p.get("old_price") and p["old_price"] > p["price"]:
            disc_pct = int(round((1 - p["price"] / p["old_price"]) * 100))
            price_str = f"<s>{texts.fmt_usd(p['old_price'])}</s> {texts.fmt_usd(p['price'])} 🔥 (-{disc_pct}%)"
        else:
            price_str = texts.fmt_usd(p['price'])
        rows.append([InlineKeyboardButton(text=f"{p['name']} — {price_str}{mark}",
                                          callback_data=f"adm:prod:{p['id']}")])
    rows.append([InlineKeyboardButton(text="🏷 Скидки / Наценки в разделе", callback_data=f"adm:price_cat:{cat_id}")])
    rows.append([InlineKeyboardButton(text="➕ Добавить товар сюда", callback_data=f"adm:add_prod:{cat_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Разделы", callback_data="adm:prods")])
    await cb.message.answer(f"📦 <b>Товары раздела «{cat_name}»:</b> ({len(prods)} шт)", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:prod:"))
async def adm_prod(cb: CallbackQuery, db: Database, bot: Bot):
    pid = int(cb.data.split(":")[2])
    p = await db.get_product(pid)
    if not p:
        return await cb.answer("Товар не найден", show_alert=True)
    
    cat = await db.get_category(p["category_id"])
    cat_name = cat["name"] if cat else "Неизвестный"
    
    if p["kind"] == "oneoff":
        stock = f"склад: {await db.stock(pid)} шт."
    else:
        stock = "многоразовый (∞)"
    vis = "показан ✅" if p["visible"] else "скрыт 🚫"
    photos_n = await db.count_product_photos(pid)

    # Генерируем deep-link на конкретный товар (для копирования)
    me = await bot.get_me()
    product_link = f"https://t.me/{me.username}?start=prod_{pid}"

    if "old_price" in p.keys() and p.get("old_price") and p["old_price"] > p["price"]:
        disc_pct = int(round((1 - p["price"] / p["old_price"]) * 100))
        price_disp = f"<s>{texts.fmt_usd(p['old_price'])}</s> <b>{texts.fmt_usd(p['price'])}</b> 🔥 <i>(-{disc_pct}%)</i>"
        has_disc = True
    else:
        price_disp = f"<b>{texts.fmt_usd(p['price'])}</b>"
        has_disc = False

    rows = [
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"adm:prod_edit:{pid}:name"),
         InlineKeyboardButton(text="✏️ Описание", callback_data=f"adm:prod_edit:{pid}:description")],
        [InlineKeyboardButton(text="✏️ Цена ($)", callback_data=f"adm:prod_edit:{pid}:price"),
         InlineKeyboardButton(text="👁 Скрыть/показать", callback_data=f"adm:prod_toggle:{pid}")],
        [InlineKeyboardButton(text="📉 Скидка (%)", callback_data=f"adm:price_op:prod:{pid}:discount"),
         InlineKeyboardButton(text="📈 Повысить (%)", callback_data=f"adm:price_op:prod:{pid}:markup")],
        [InlineKeyboardButton(text=f"📷 Фото ({photos_n})", callback_data=f"adm:prod_photos:{pid}")],
        [InlineKeyboardButton(text="🔀 Переместить в другой раздел", callback_data=f"adm:prod_move:{pid}")],
        [InlineKeyboardButton(text="👁 Просмотр как пользователь", callback_data=f"adm:prod_preview:{pid}")],
    ]
    if has_disc:
        rows.append([InlineKeyboardButton(text="🔄 Сбросить скидку (вернуть старую цену)", callback_data=f"adm:price_reset:prod:{pid}")])
    if p["kind"] == "oneoff":
        # Позволяет напрямую установить числовое количество на складе
        rows.append([
            InlineKeyboardButton(text="✏️ Количество", callback_data=f"adm:prod_stock:{pid}"),
            InlineKeyboardButton(text="➕ Добавить единицы", callback_data=f"adm:prod_items:{pid}")
        ])
    rows.append([InlineKeyboardButton(text="❌ Удалить товар", callback_data=f"adm:prod_del:{pid}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm:pcat:{p['category_id']}")])
    await cb.message.answer(
        f"📦 <b>{p['name']}</b>\n"
        f"📁 Раздел: <b>{cat_name}</b>\n"
        f"{p['description']}\n\n"
        f"💵 Цена: {price_disp}\n"
        f"📷 Фото: {photos_n} | {stock}\n"
        f"Статус: {vis}\n\n"
        f"🔗 <b>Ссылка на товар:</b>\n<code>{product_link}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:prod_move:"))
async def adm_prod_move(cb: CallbackQuery, db: Database):
    pid = int(cb.data.split(":")[2])
    p = await db.get_product(pid)
    if not p:
        return await cb.answer("Товар не найден", show_alert=True)
    
    all_cats = await db.list_all_categories_flat()
    rows = []
    for c in all_cats:
        if c["id"] == p["category_id"]:
            rows.append([InlineKeyboardButton(text=f"{c['display_name']} (текущий ✅)", callback_data="noop")])
        else:
            rows.append([InlineKeyboardButton(text=f"{c['display_name']} ➔ Сюда", callback_data=f"adm:prod_move_to:{pid}:{c['id']}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад к товару", callback_data=f"adm:prod:{pid}")])
    
    await cb.message.answer(
        f"🔀 <b>Перемещение товара «{p['name']}»</b>\n\n"
        "Выберите раздел или подраздел, куда хотите перенести этот товар:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:prod_move_to:"))
async def adm_prod_move_to(cb: CallbackQuery, db: Database, bot: Bot):
    parts = cb.data.split(":")
    pid = int(parts[2])
    new_cat_id = int(parts[3])
    
    p = await db.get_product(pid)
    if not p:
        return await cb.answer("Товар не найден", show_alert=True)
    
    new_cat = await db.get_category(new_cat_id)
    if not new_cat:
        return await cb.answer("Новый раздел не найден", show_alert=True)
    
    await db.move_product(pid, new_cat_id)
    await cb.answer(f"✅ Товар перенесён в «{new_cat['name']}»!", show_alert=True)
    await adm_prod(cb, db, bot)


@router.callback_query(F.data.startswith("adm:prod_preview:"))
async def adm_prod_preview(cb: CallbackQuery, db: Database):
    """Показывает карточку товара так как видит её пользователь."""
    pid = int(cb.data.split(":")[2])
    p = await db.get_product(pid)
    if not p:
        return await cb.answer("Товар не найден", show_alert=True)

    from media import send_product_photos
    photos = await db.list_product_photos(pid)
    file_ids = [ph["file_id"] for ph in photos]

    stock = "многоразовый (∞)" if p["kind"] == "reusable" else f"{await db.stock(pid)} шт."

    buy_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🛒 Купить — {texts.fmt_usd(p['price'])}", callback_data=f"buy:{pid}")],
        [InlineKeyboardButton(text="⬅️ К товару (адм)", callback_data=f"adm:prod:{pid}")],
    ])

    caption = (
        f"📦 <b>{p['name']}</b>\n\n"
        f"{p['description']}\n\n"
        f"💵 Цена: <b>{texts.fmt_usd(p['price'])}</b>\n"
        f"📦 В наличии: {stock}\n\n"
        f"<i>👆 Так видит товар пользователь</i>"
    )

    try:
        await send_product_photos(cb.message, file_ids, caption, buy_markup)
    except Exception:
        await cb.message.answer(caption, reply_markup=buy_markup, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:add_prod:"))
async def adm_add_prod(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ProdAdd.name)
    await state.update_data(category_id=int(cb.data.split(":")[2]))
    await cb.message.answer("Введите название товара:")
    await cb.answer()



@router.message(ProdAdd.name, F.text)
async def adm_add_prod_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(ProdAdd.description)
    await message.answer("Введите описание товара (или «-» чтобы оставить пустым):")


@router.message(ProdAdd.description, F.text)
async def adm_add_prod_desc(message: Message, state: FSMContext):
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(ProdAdd.price)
    await message.answer("Введите цену в долларах (например, 5 или 7.50).\n"
                         "Для бесплатного товара введите 0:")


@router.message(ProdAdd.price, F.text)
async def adm_add_prod_price(message: Message, state: FSMContext):
    try:
        price = round(float(message.text.replace(",", ".").replace("$", "").strip()), 2)
    except ValueError:
        return await message.answer("Не понял цену. Введите число, например 5, 7.50 или 0:")
    if price < 0:
        return await message.answer("Цена не может быть отрицательной. Введите ещё раз:")
    await state.update_data(price=int(round(price * 100)))
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣ Одноразовый (склад единиц)", callback_data="adm:kind:oneoff")],
        [InlineKeyboardButton(text="♾ Многоразовый (общий контент)", callback_data="adm:kind:reusable")],
    ])
    await message.answer("Выберите тип товара:", reply_markup=markup)


@router.callback_query(F.data.startswith("adm:kind:"))
async def adm_add_prod_kind(cb: CallbackQuery, db: Database, state: FSMContext):
    kind = cb.data.split(":")[2]
    data = await state.get_data()
    if not data.get("name"):
        return await cb.answer("Начните добавление товара заново", show_alert=True)
    if kind == "reusable":
        await state.set_state(ProdAdd.content)
        await cb.message.answer("Пришлите содержимое товара: текст (ключ, ссылка...) или файл:")
    else:
        pid = await db.add_product(data["category_id"], data["name"], data["description"],
                                  data["price"], "oneoff")
        await state.update_data(product_id=pid, added=0)
        await state.set_state(ProdAdd.items)
        await cb.message.answer(
            "Товар создан. Теперь загрузите единицы:\n"
            "• текстовое сообщение — каждая строка станет отдельной единицей;\n"
            "• файл — одна единица.\n"
            "Когда закончите — отправьте /done.")
    await cb.answer()


async def start_add_photos(message: Message, state: FSMContext, product_id: int, note: str = "") -> None:
    await state.update_data(product_id=product_id, photos_added=0)
    await state.set_state(ProdAdd.photos)
    prefix = f"{note}\n\n" if note else ""
    await message.answer(
        f"{prefix}📷 Пришлите фото товара (можно несколько, до {MAX_PHOTOS}).\n"
        "Когда закончите — /done. Чтобы пропустить — /skip.")


@router.message(ProdAdd.content)
async def adm_add_prod_content(message: Message, db: Database, state: FSMContext):
    item = item_of(message)
    if not item:
        return await message.answer("Пришлите текст или файл:")
    data = await state.get_data()
    pid = await db.add_product(data["category_id"], data["name"], data["description"],
                               data["price"], "reusable", item[0], item[1])
    await start_add_photos(message, state, pid, "✅ Товар создан.")


@router.message(ProdAdd.items, Command("done"))
async def adm_add_prod_items_done(message: Message, state: FSMContext):
    data = await state.get_data()
    await start_add_photos(
        message, state, data["product_id"],
        f"✅ Единицы загружены: {data.get('added', 0)}.")


@router.message(ProdAdd.items)
async def adm_add_prod_items(message: Message, db: Database, state: FSMContext):
    data = await state.get_data()
    added = await load_items(message, db, data["product_id"])
    if added == 0:
        return await message.answer("Пришлите текст (строка = единица) или файл, либо /done:")
    total = data.get("added", 0) + added
    await state.update_data(added=total)
    await message.answer(f"➕ Добавлено: {added}. Всего: {total}. Ещё или /done.")


@router.message(ProdAdd.photos, Command("done"))
@router.message(ProdAdd.photos, Command("skip"))
async def adm_add_prod_photos_done(message: Message, state: FSMContext, db: Database, config=None):
    data = await state.get_data()
    pid = data.get("product_id")
    n = data.get("photos_added", 0)
    await state.clear()
    await message.answer(f"✅ Товар готов. Фото: {n}.", reply_markup=admin_menu_kb())
    if pid and config:
        from autopost import send_product_autopost
        await send_product_autopost(message.bot, db, pid, config)


@router.message(ProdAdd.photos)
async def adm_add_prod_photos(message: Message, db: Database, state: FSMContext, bot: Bot):
    file_id = photo_file_id(message)
    if not file_id:
        return await message.answer("Пришлите фото, либо /done / /skip:")
    data = await state.get_data()
    current = await db.count_product_photos(data["product_id"])
    if current >= MAX_PHOTOS:
        return await message.answer(
            f"Достигнут лимит {MAX_PHOTOS} фото. Отправьте /done.")
    # Скачиваем и сохраняем локально
    saved = await download_and_save_photo(bot, file_id, data["product_id"], current + 1)
    await db.add_product_photo(data["product_id"], saved)
    total = data.get("photos_added", 0) + 1
    await state.update_data(photos_added=total)
    left = MAX_PHOTOS - current - 1
    await message.answer(f"📷 Фото добавлено ({total}). Осталось слотов: {left}. Ещё или /done.")


@router.callback_query(F.data.startswith("adm:prod_edit:"))
async def adm_prod_edit(cb: CallbackQuery, state: FSMContext):
    _, _, pid, field = cb.data.split(":")
    await state.set_state(ProdEdit.value)
    await state.update_data(product_id=int(pid), field=field)
    prompts = {
        "name": "Введите новое название:",
        "description": "Введите новое описание:",
        "price": "Введите новую цену в долларах (0 = бесплатно):",
    }
    await cb.message.answer(prompts[field])
    await cb.answer()


@router.message(ProdEdit.value, F.text)
async def adm_prod_edit_done(message: Message, db: Database, state: FSMContext):
    data = await state.get_data()
    value = message.text.strip()
    if data["field"] == "price":
        try:
            price = round(float(value.replace(",", ".").replace("$", "")), 2)
        except ValueError:
            return await message.answer("Не понял цену. Введите число (можно 0):")
        if price < 0:
            return await message.answer("Цена не может быть отрицательной:")
        value = int(round(price * 100))
    await db.set_product_field(data["product_id"], data["field"], value)
    await state.clear()
    await message.answer("✅ Сохранено.", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("adm:prod_stock:"))
async def adm_prod_stock(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split(":")[2])
    await state.set_state(ProdStock.stock)
    await state.update_data(product_id=pid)
    await cb.message.answer("Введите количество единиц на складе (целое неотрицательное число).\nЧтобы снять ручное значение, отправьте 'clear' или 'сброс'.")
    await cb.answer()


@router.message(ProdStock.stock)
async def adm_prod_stock_done(message: Message, db: Database, state: FSMContext):
    data = await state.get_data()
    pid = data.get("product_id")
    if not pid:
        await state.clear()
        return await message.answer("Что-то пошло не так. Попробуйте снова.", reply_markup=admin_menu_kb())
    text = message.text.strip().lower()
    if text in ("clear", "сброс", "удалить"):
        await db.set_product_stock(pid, None)
        await state.clear()
        await message.answer("✅ Переопределение количества снято.", reply_markup=admin_menu_kb())
        return
    try:
        count = int(message.text.strip())
        if count < 0:
            raise ValueError()
    except ValueError:
        return await message.answer("Нужно ввести неотрицательное целое число или 'clear'. Попробуйте ещё раз:")
    await db.set_product_stock(pid, count)
    await state.clear()
    await message.answer(f"✅ Количество установлено: {count} шт.", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("adm:prod_toggle:"))
async def adm_prod_toggle(cb: CallbackQuery, db: Database):
    await db.toggle_visible(int(cb.data.split(":")[2]))
    await cb.answer("Готово ✅")


@router.callback_query(F.data.startswith("adm:prod_items:"))
async def adm_prod_items(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ProdItems.items)
    await state.update_data(product_id=int(cb.data.split(":")[2]), added=0)
    await cb.message.answer("Загрузите единицы (текст: строка = единица; файл = единица). Готово — /done.")
    await cb.answer()


@router.message(ProdItems.items, Command("done"))
async def adm_prod_items_done(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await message.answer(f"✅ Готово, загружено единиц: {data.get('added', 0)}.",
                         reply_markup=admin_menu_kb())


@router.message(ProdItems.items)
async def adm_prod_items_load(message: Message, db: Database, state: FSMContext):
    data = await state.get_data()
    added = await load_items(message, db, data["product_id"])
    if added == 0:
        return await message.answer("Пришлите текст или файл, либо /done:")
    total = data.get("added", 0) + added
    await state.update_data(added=total)
    await message.answer(f"➕ Добавлено: {added}. Всего: {total}. Ещё или /done.")


# --- фото товаров ---

@router.callback_query(F.data.startswith("adm:prod_photos:"))
async def adm_prod_photos(cb: CallbackQuery, db: Database):
    pid = int(cb.data.split(":")[2])
    p = await db.get_product(pid)
    if not p:
        return await cb.answer("Товар не найден", show_alert=True)
    photos = await db.list_product_photos(pid)
    rows = [
        [InlineKeyboardButton(text="➕ Добавить фото", callback_data=f"adm:prod_photo_add:{pid}")],
    ]
    if photos:
        rows.append([InlineKeyboardButton(text="🗑 Удалить все фото",
                                          callback_data=f"adm:prod_photo_clear:{pid}")])
        for i, ph in enumerate(photos, 1):
            rows.append([InlineKeyboardButton(
                text=f"🗑 Удалить фото #{i}",
                callback_data=f"adm:prod_photo_del:{ph['id']}:{pid}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm:prod:{pid}")])
    await cb.message.answer(
        f"📷 Фото товара «{p['name']}»: {len(photos)}/{MAX_PHOTOS}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:prod_photo_add:"))
async def adm_prod_photo_add(cb: CallbackQuery, db: Database, state: FSMContext):
    pid = int(cb.data.split(":")[2])
    current = await db.count_product_photos(pid)
    if current >= MAX_PHOTOS:
        return await cb.answer(f"Лимит {MAX_PHOTOS} фото уже достигнут", show_alert=True)
    await state.set_state(ProdPhotos.photos)
    await state.update_data(product_id=pid, photos_added=0)
    await cb.message.answer(
        f"Пришлите фото (можно несколько). Свободно слотов: {MAX_PHOTOS - current}.\n"
        "Готово — /done.")
    await cb.answer()


@router.message(ProdPhotos.photos, Command("done"))
async def adm_prod_photos_done(message: Message, state: FSMContext):
    data = await state.get_data()
    n = data.get("photos_added", 0)
    pid = data.get("product_id")
    await state.clear()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ К товару", callback_data=f"adm:prod:{pid}")]
    ]) if pid else admin_menu_kb()
    await message.answer(f"✅ Добавлено фото: {n}.", reply_markup=markup)


@router.message(ProdPhotos.photos)
async def adm_prod_photos_load(message: Message, db: Database, state: FSMContext, bot: Bot):
    file_id = photo_file_id(message)
    if not file_id:
        return await message.answer("Пришлите фото или /done:")
    data = await state.get_data()
    current = await db.count_product_photos(data["product_id"])
    if current >= MAX_PHOTOS:
        return await message.answer(f"Лимит {MAX_PHOTOS} фото. Отправьте /done.")
    # Сохраняем локально
    saved = await download_and_save_photo(bot, file_id, data["product_id"], current + 1)
    await db.add_product_photo(data["product_id"], saved)
    total = data.get("photos_added", 0) + 1
    await state.update_data(photos_added=total)
    await message.answer(
        f"📷 Добавлено ({total}). Свободно: {MAX_PHOTOS - current - 1}. Ещё или /done.")


async def _show_prod_photos(message, db: Database, pid: int) -> None:
    p = await db.get_product(pid)
    if not p:
        return
    photos = await db.list_product_photos(pid)
    rows = [
        [InlineKeyboardButton(text="➕ Добавить фото", callback_data=f"adm:prod_photo_add:{pid}")],
    ]
    if photos:
        rows.append([InlineKeyboardButton(text="🗑 Удалить все фото",
                                          callback_data=f"adm:prod_photo_clear:{pid}")])
        for i, ph in enumerate(photos, 1):
            rows.append([InlineKeyboardButton(
                text=f"🗑 Удалить фото #{i}",
                callback_data=f"adm:prod_photo_del:{ph['id']}:{pid}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm:prod:{pid}")])
    await message.answer(
        f"📷 Фото товара «{p['name']}»: {len(photos)}/{MAX_PHOTOS}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("adm:prod_photos:"))
async def adm_prod_photos(cb: CallbackQuery, db: Database):
    pid = int(cb.data.split(":")[2])
    if not await db.get_product(pid):
        return await cb.answer("Товар не найден", show_alert=True)
    await _show_prod_photos(cb.message, db, pid)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:prod_photo_del:"))
async def adm_prod_photo_del(cb: CallbackQuery, db: Database):
    # adm:prod_photo_del:{photo_id}:{product_id}
    parts = cb.data.split(":")
    photo_id, pid = int(parts[2]), int(parts[3])
    await db.delete_product_photo(photo_id)
    await cb.answer("Фото удалено ✅")
    await _show_prod_photos(cb.message, db, pid)


@router.callback_query(F.data.startswith("adm:prod_photo_clear:"))
async def adm_prod_photo_clear(cb: CallbackQuery, db: Database):
    pid = int(cb.data.split(":")[2])
    await db.clear_product_photos(pid)
    await cb.answer("Все фото удалены ✅")
    await _show_prod_photos(cb.message, db, pid)


@router.message(Command("migrate_photos"))
async def adm_migrate_photos(message: Message, db: Database, bot: Bot):
    await message.answer("Начинаю миграцию фото — это может занять время...")
    cur = await db.conn.execute("SELECT * FROM product_photos ORDER BY product_id, position, id")
    rows = await cur.fetchall()
    migrated = 0
    failed = 0
    for r in rows:
        old = r['file_id']
        pid = r['product_id']
        if not old or old.startswith('photos/') or old.startswith('http') or old.startswith('file_id:'):
            continue
        try:
            saved = await download_and_save_photo(bot, old, pid, r.get('position', 0) if isinstance(r.get('position', None), int) else 0)
            await db.conn.execute("UPDATE product_photos SET file_id = ? WHERE id = ?", (saved, r['id']))
            await db.conn.commit()
            migrated += 1
        except Exception as e:
            print('migrate error', e)
            failed += 1
    await message.answer(f"Миграция завершена. Успешно: {migrated}. Не удалось: {failed}.")


@router.callback_query(F.data.startswith("adm:prod_del_yes:"))
async def adm_prod_del_yes(cb: CallbackQuery, db: Database):
    await db.delete_product(int(cb.data.split(":")[2]))
    await cb.message.answer("🗑 Товар удалён.", reply_markup=admin_menu_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("adm:prod_del:"))
async def adm_prod_del(cb: CallbackQuery):
    pid = int(cb.data.split(":")[2])
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Да, удалить", callback_data=f"adm:prod_del_yes:{pid}")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"adm:prod:{pid}")],
    ])
    await cb.message.answer("Удалить товар?", reply_markup=markup)
    await cb.answer()


# --- пользователи ---

@router.callback_query(F.data == "adm:users")
async def adm_users(cb: CallbackQuery, state: FSMContext):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск пользователя", callback_data="adm:user_search")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
    ])
    await cb.message.answer("👥 Управление пользователями:", reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data == "adm:user_search")
async def adm_user_search(cb: CallbackQuery, state: FSMContext):
    await state.set_state(UserSearch.query)
    await cb.message.answer("Введите ID или @username пользователя для поиска:")
    await cb.answer()


@router.message(UserSearch.query)
async def adm_user_search_result(message: Message, db: Database, state: FSMContext):
    query = message.text.strip()
    user = await db.search_users(query)
    
    if not user:
        await message.answer("❌ Пользователь не найден. Попробуйте ещё раз:")
        return
    
    if isinstance(user, list):
        if len(user) > 1:
            rows = [[InlineKeyboardButton(text=f"@{u['username']} (ID: {u['id']})", 
                                        callback_data=f"adm:user_info:{u['id']}")] for u in user]
            rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:users")])
            await message.answer("Найдено несколько пользователей:", 
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            await state.clear()
            return
        user = user[0]
    
    await state.clear()
    await show_user_info(message, db, user['id'])


async def show_user_info(message: Message, db: Database, user_id: int):
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден")
        return
    
    logs = await db.get_user_logs(user_id, limit=5)
    
    text = f"👤 Информация о пользователе\n\n"
    text += f"ID: {user['id']}\n"
    text += f"Username: @{user['username'] or 'не указан'}\n"
    currency = user['currency'] if user and 'currency' in user.keys() else 'USD'
    text += f"Баланс: {texts.fmt_balance(user['balance'], currency)}\n"
    text += f"Дата создания: {user['created_at']}\n"
    
    if logs:
        text += f"\n📋 Последние логи ({len(logs)}):\n"
        for log in reversed(logs):
            text += f"• {log['action']}"
            if log['details']:
                text += f" — {log['details']}"
            text += f" ({log['created_at']})\n"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Все логи", callback_data=f"adm:user_logs:{user_id}")],
        [InlineKeyboardButton(text="➕ Пополнить баланс", callback_data=f"adm:add_balance:{user_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:users")],
    ])
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("adm:user_info:"))
async def adm_user_info(cb: CallbackQuery, db: Database):
    user_id = int(cb.data.split(":")[2])
    await show_user_info(cb.message, db, user_id)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:user_logs:"))
async def adm_user_logs(cb: CallbackQuery, db: Database):
    user_id = int(cb.data.split(":")[2])
    user = await db.get_user(user_id)
    logs = await db.get_user_logs(user_id, limit=50)
    
    text = f"📋 Логи @{user['username'] or 'неизвестен'} (ID: {user_id})\n\n"
    if logs:
        for log in reversed(logs):
            text += f"• {log['action']}"
            if log['details']:
                text += f" — {log['details']}"
            text += f"\n  {log['created_at']}\n"
    else:
        text += "Нет логов"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm:user_info:{user_id}")],
    ])
    await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:add_balance:"))
async def adm_add_balance(cb: CallbackQuery, state: FSMContext):
    user_id = int(cb.data.split(":")[2])
    await state.set_state(AddBalance.user_id)
    await state.update_data(user_id=user_id)
    await cb.message.answer("Введите сумму для добавления на баланс (в центах, например 1000 = $10.00):")
    await cb.answer()


@router.message(AddBalance.user_id)
async def adm_add_balance_amount(message: Message, db: Database, state: FSMContext):
    try:
       amount = int(message.text.strip())
       if amount <= 0:
           await message.answer("Сумма должна быть больше нуля. Попробуйте ещё раз:")
           return
    except ValueError:
       await message.answer("Введите число. Попробуйте ещё раз:")
       return
    
    data = await state.get_data()
    user_id = data['user_id']
    user = await db.get_user(user_id)
    
    await db.add_balance(user_id, amount)
    await db.add_log(user_id, user['username'] if user else None, "баланс_добавлен_админом",
                   f"{texts.fmt_usd(amount)}")
    
    await state.clear()
    await message.answer(f"✅ На баланс пользователя добавлено {texts.fmt_usd(amount)}",
                       reply_markup=admin_menu_kb())


# --- логи ---

@router.callback_query(F.data == "adm:logs")
async def adm_logs(cb: CallbackQuery, db: Database):
    logs = await db.list_all_logs(limit=20)
    
    text = "📋 Последние логи шопа\n\n"
    if logs:
        for log in reversed(logs):
            text += f"👤 @{log['username'] or 'неизвестен'}\n"
            text += f"• {log['action']}"
            if log['details']:
                text += f" — {log['details']}"
            text += f"\n  {log['created_at']}\n\n"
    else:
        text += "Нет логов"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
    ])
    await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


# --- рассылка ---

@router.callback_query(F.data == "adm:mailing")
async def adm_mailing(cb: CallbackQuery, db: Database):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Новая рассылка", callback_data="adm:mailing_new")],
        [InlineKeyboardButton(text="📊 История рассылок", callback_data="adm:mailing_history")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")],
    ])
    await cb.message.answer("📨 Рассылка сообщений:", reply_markup=markup)
    await cb.answer()


@router.callback_query(F.data == "adm:mailing_new")
async def adm_mailing_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(MailingMessage.text)
    await cb.message.answer("Введите текст сообщения для рассылки всем пользователям:")
    await cb.answer()


@router.message(MailingMessage.text)
async def adm_mailing_send(message: Message, db: Database, state: FSMContext, bot: Bot):
    text = message.text.strip()
    if not text:
        await message.answer("Сообщение не может быть пустым. Попробуйте ещё раз:")
        return
    
    users = await db.list_all_users()
    mailing_id = await db.create_mailing(text, message.from_user.username or f"user_{message.from_user.id}",
                                         [u['id'] for u in users])
    
    await state.clear()
    await message.answer(f"✅ Рассылка создана. Всего пользователей: {len(users)}\n"
                        f"Рассылка начнётся в фоне.", reply_markup=admin_menu_kb())
    
    # Отправляем сообщения в фоне
    for user_id in [u['id'] for u in users]:
        try:
            await bot.send_message(user_id, f"📨 Новое сообщение от администратора:\n\n{text}")
        except Exception:
            pass


@router.callback_query(F.data == "adm:mailing_history")
async def adm_mailing_history(cb: CallbackQuery, db: Database):
    cur = await db.conn.execute(
        "SELECT id, message_text, created_by_admin, created_at, sent_count, total_count FROM mailings "
        "ORDER BY created_at DESC LIMIT 10"
    )
    mailings = await cur.fetchall()
    
    text = "📨 История рассылок\n\n"
    if mailings:
        for m in mailings:
            progress = f"{m['sent_count']}/{m['total_count']}" if m['total_count'] else "0/0"
            text += f"ID: {m['id']}\n"
            text += f"От: @{m['created_by_admin']}\n"
            text += f"Статус: {progress}\n"
            text += f"Дата: {m['created_at']}\n"
            text += f"Текст: {m['message_text'][:50]}...\n\n"
    else:
        text += "Рассылок нет"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:mailing")],
    ])
    await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


# --- статистика ---

@router.callback_query(F.data == "adm:stats")
async def adm_stats(cb: CallbackQuery, db: Database):
    s = await db.stats()
    lines = [
        "📊 Статистика",
        f"👥 Пользователей: {s['users']}",
        f"🛒 Продаж: {s['sales']}",
        f"💰 Выручка: {texts.fmt_usd(s['revenue'])}",
    ]
    if s["top"]:
        lines.append("\n🏆 Топ товаров:")
        for row in s["top"]:
            lines.append(f"• {row['product_name']} — {row['c']} шт.")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")]])
    await cb.message.answer("\n".join(lines), reply_markup=markup)
    await cb.answer()


# --- Управление выплатами зеркал ---

@router.callback_query(F.data == "adm:withdrawals")
async def adm_withdrawals_list(cb: CallbackQuery, db: Database):
    reqs = await db.list_pending_withdrawals()
    if not reqs:
        await cb.message.answer("💳 Активных заявок на вывод от зеркал нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")]]))
        await cb.answer()
        return

    text = "💳 **Заявки на вывод средств от Зеркал:**\n\n"
    keyboard = []
    for r in reqs:
        mirror = await db.get_mirror_by_id(r["mirror_id"])
        bot_name = mirror["bot_username"] if mirror else "unknown"
        text += f"ID: #{r['id']} | @{bot_name} | Сумма: {r['amount']} ₽\nРеквизиты: `{r['requisites']}`\n\n"
        keyboard.append([
            InlineKeyboardButton(text=f"✅ Подтвердить #{r['id']}", callback_data=f"adm:w_appr:{r['id']}"),
            InlineKeyboardButton(text=f"❌ Отклонить #{r['id']}", callback_data=f"adm:w_rej:{r['id']}")
        ])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:w_appr:"))
async def adm_withdraw_approve(cb: CallbackQuery, db: Database, bot: Bot):
    req_id = int(cb.data.split(":")[2])
    ok = await db.process_withdrawal(req_id, "completed")
    if ok:
        await cb.message.answer(f"✅ Заявка #{req_id} помечена как выплаченная!")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:w_rej:"))
async def adm_withdraw_reject(cb: CallbackQuery, db: Database):
    req_id = int(cb.data.split(":")[2])
    ok = await db.process_withdrawal(req_id, "rejected")
    if ok:
        await cb.message.answer(f"❌ Заявка #{req_id} отклонена, средства вернулись зеркалу!")
    await cb.answer()


# --- Создание Промокодов ---

class PromoCreateState(StatesGroup):
    waiting_for_details = State()


@router.callback_query(F.data == "adm:create_promo")
async def adm_create_promo_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(PromoCreateState.waiting_for_details)
    await cb.message.answer(
        "🎫 <b>Создание Промокода</b>\n\n"
        "Отправьте данные в формате:\n"
        "<code>КОД СУММА ВСЕГО_АКТИВАЦИЙ АКТИВАЦИЙ_НА_ПОЛЬЗОВАТЕЛЯ</code>\n\n"
        "📌 Примеры:\n"
        "• <code>SUMMER 100 50 1</code> — код на 100₽, 50 активаций, 1 на пользователя\n"
        "• <code>VIP500 500 10 3</code> — код на 500₽, 10 активаций, 3 на пользователя\n\n"
        "💡 Если не указать последний параметр — по умолчанию 1 активация на пользователя.",
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(PromoCreateState.waiting_for_details)
async def adm_create_promo_process(message: Message, state: FSMContext, db: Database):
    parts = message.text.strip().split()
    if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer(
            "❌ Неверный формат!\nВведите: <code>КОД СУММА ВСЕГО_АКТИВАЦИЙ [НА_ПОЛЬЗОВАТЕЛЯ]</code>\n"
            "Пример: <code>SUMMER 100 50 1</code>",
            parse_mode="HTML"
        )
        return

    code = parts[0]
    amount = int(parts[1])
    max_uses = int(parts[2])
    max_per_user = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else 1

    ok = await db.create_promocode(code, "bonus", amount, max_uses, max_per_user)
    await state.clear()
    if ok:
        await message.answer(
            f"🎉 Промокод создан!\n\n"
            f"🔑 Код: <code>{code.upper()}</code>\n"
            f"💰 Сумма: <b>{amount} ₽</b>\n"
            f"🔢 Всего активаций: <b>{max_uses}</b>\n"
            f"👤 На одного пользователя: <b>{max_per_user}</b>",
            parse_mode="HTML",
            reply_markup=admin_menu_kb()
        )
    else:
        await message.answer("❌ Ошибка! Возможно, такой промокод уже существует.")


# ─────────────────────────────────────────────
# 🎨  ДИЗАЙН КНОПОК ГЛАВНОГО МЕНЮ
# ─────────────────────────────────────────────

# Все кнопки: ключ -> (эмодзи, label, дефолтный текст)
DESIGN_BUTTONS = [
    ("search",       "💎", "Поиск",           texts.BTN_SEARCH),
    ("catalog",      "💎", "Каталог",         texts.BTN_CATALOG),
    ("profile",      "💎", "Профиль",         texts.BTN_PROFILE),
    ("support",      "💎", "Поддержка",       texts.BTN_SUPPORT),
    ("ads",          "💎", "Реклама",         "💎 Реклама"),
    ("history",      "💎", "История",         texts.BTN_HISTORY),
    ("referral",     "💎", "Рефералка",       texts.BTN_REFERRAL),
    ("about",        "💎", "О магазине",      "💎 О магазине"),
    ("reviews",      "💎", "Отзывы",          "💎 Отзывы"),
    ("create_check", "💎", "Создать чек",     "💎 Создать чек"),
    ("promocode",    "💎", "Промокод",        "💎 Промокод"),
    ("more",         "💎", "Ещё",             "💎 Ещё"),
]


class BtnEditState(StatesGroup):
    waiting_value = State()


class LinkEditState(StatesGroup):
    waiting_url = State()


class AutopostChannelState(StatesGroup):
    waiting_channel = State()


async def _build_btns_menu(db: Database) -> str:
    """Формирует текст с текущими значениями кнопок."""
    lines = ["🎨 <b>Дизайн кнопок и баннеров меню</b>\n"]
    banner = await db.get_setting("btn:banner")
    lines.append(f"🖼 <b>Глобальный баннер меню:</b> {'✅ Установлен' if banner else '❌ Не установлен'}\n")
    for key, emoji, label, default in DESIGN_BUTTONS:
        current = await db.get_setting(f"btn:{key}") or default
        pb = await db.get_setting(f"btn:banner:{key}")
        b_mark = " 🖼✅" if pb else ""
        changed = " ✏️" if current != default else ""
        lines.append(f"{emoji} <b>{label}</b>{changed}{b_mark}\n└ <code>{current}</code>")
    lines.append("\n<i>Нажмите на кнопку чтобы изменить текст или баннер (фото/GIF/видео).</i>")
    return "\n".join(lines)


@router.callback_query(F.data == "adm:btns")
async def adm_btns(cb: CallbackQuery, db: Database):
    text = await _build_btns_menu(db)
    rows = []
    
    # Кнопка глобального баннера
    gb = await db.get_setting("btn:banner")
    gb_text = "🖼 Глобальный баннер: ✅ Изменить" if gb else "🖼 Глобальный баннер: ➕ Добавить"
    rows.append([InlineKeyboardButton(text=gb_text, callback_data="adm:btn_banner")])
    if gb:
        rows.append([InlineKeyboardButton(text="🗑 Удалить глобальный баннер", callback_data="adm:btn_banner_del")])

    # Кнопки для каждого раздела
    for key, emoji, label, default in DESIGN_BUTTONS:
        current = await db.get_setting(f"btn:{key}") or default
        pb = await db.get_setting(f"btn:banner:{key}")
        b_status = "🖼✅" if pb else "🖼➕"
        
        rows.append([
            InlineKeyboardButton(text=f"✏️ {emoji} {label}", callback_data=f"adm:btn_edit:{key}"),
            InlineKeyboardButton(text=f"{b_status} Баннер", callback_data=f"adm:btn_banner:{key}")
        ])

    rows.append([InlineKeyboardButton(text="🔄 Сбросить все тексты к дефолту", callback_data="adm:btn_reset_all")])
    rows.append([InlineKeyboardButton(text="⬅️ Админ-меню", callback_data="adm:menu")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:btn_edit:"))
async def adm_btn_edit(cb: CallbackQuery, db: Database, state: FSMContext):
    key = cb.data.split(":")[2]
    meta = next((b for b in DESIGN_BUTTONS if b[0] == key), None)
    if not meta:
        return await cb.answer("Кнопка не найдена", show_alert=True)

    _, emoji, label, default = meta
    current = await db.get_setting(f"btn:{key}") or default

    await state.set_state(BtnEditState.waiting_value)
    await state.update_data(btn_key=key, btn_label=label, btn_default=default)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔄 Сбросить к дефолту: {default}", callback_data=f"adm:btn_reset:{key}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:btns")],
    ])
    await cb.message.answer(
        f"✏️ Редактирование кнопки <b>{emoji} {label}</b>\n\n"
        f"Текущий текст: <code>{current}</code>\n"
        f"По умолчанию: <code>{default}</code>\n\n"
        f"Введите новый текст кнопки (или нажмите «Сбросить»):",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(BtnEditState.waiting_value, F.text)
async def adm_btn_edit_save(message: Message, db: Database, state: FSMContext):
    data = await state.get_data()
    key = data.get("btn_key")
    label = data.get("btn_label")
    default = data.get("btn_default")

    if not key:
        await state.clear()
        return

    new_text = message.text.strip()
    if len(new_text) > 128:
        return await message.answer("❌ Текст кнопки слишком длинный (максимум 128 символов). Попробуйте ещё раз:")
    if not new_text:
        return await message.answer("❌ Текст не может быть пустым. Попробуйте ещё раз:")

    await db.set_setting(f"btn:{key}", new_text)
    await state.clear()

    rows = [[InlineKeyboardButton(text=new_text, callback_data="noop")]]
    rows.append([InlineKeyboardButton(text="⬅️ К кнопкам", callback_data="adm:btns")])
    await message.answer(
        f"✅ Кнопка <b>{label}</b> обновлена!\n\n"
        f"Было: <code>{default}</code>\n"
        f"Стало: <code>{new_text}</code>\n\n"
        f"👇 Превью:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm:btn_reset:"))
async def adm_btn_reset(cb: CallbackQuery, db: Database, state: FSMContext):
    key = cb.data.split(":")[2]
    meta = next((b for b in DESIGN_BUTTONS if b[0] == key), None)
    if not meta:
        return await cb.answer("Кнопка не найдена", show_alert=True)

    _, emoji, label, default = meta
    await db.set_setting(f"btn:{key}", default)
    await state.clear()

    await cb.message.answer(
        f"🔄 Кнопка <b>{emoji} {label}</b> сброшена к дефолту: <code>{default}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К кнопкам", callback_data="adm:btns")]
        ])
    )
    await cb.answer("✅ Сброшено!")


@router.callback_query(F.data == "adm:btn_reset_all")
async def adm_btn_reset_all(cb: CallbackQuery, db: Database):
    for key, _, _, default in DESIGN_BUTTONS:
        await db.set_setting(f"btn:{key}", default)
    await cb.answer("✅ Все кнопки сброшены к дефолту!", show_alert=True)
    await adm_btns(cb, db)


# ─────────────────────────────────────────────
# 🔗  ССЫЛКИ (поддержка и другие)
# ─────────────────────────────────────────────

DESIGN_LINKS = [
    ("support_url",        "💬", "Поддержка (основная)",      "https://t.me/"),
    ("support_backup_url", "🆘", "Резервная поддержка (бот)", "https://t.me/glock_admin_bot"),
    ("channel_url",        "📢", "Канал магазина",            "https://t.me/news_glock_shop"),
    ("our_projects_url",   "❇️", "Наши проекты (ссылка)",     "https://t.me/"),
]


@router.callback_query(F.data == "adm:links")
async def adm_links(cb: CallbackQuery, db: Database):
    lines = ["🔗 <b>Управление ссылками</b>\n"]
    rows = []
    for key, emoji, label, default in DESIGN_LINKS:
        current = await db.get_setting(f"link:{key}") or default
        changed = " ✏️" if current != default else ""
        lines.append(f"{emoji} <b>{label}</b>{changed}\n└ <code>{current}</code>")
        rows.append([InlineKeyboardButton(
            text=f"{emoji} {label}{changed}",
            callback_data=f"adm:link_edit:{key}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="adm:menu")])
    await cb.message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:link_edit:"))
async def adm_link_edit(cb: CallbackQuery, db: Database, state: FSMContext):
    key = cb.data.split(":")[2]
    meta = next((l for l in DESIGN_LINKS if l[0] == key), None)
    if not meta:
        return await cb.answer("Ссылка не найдена", show_alert=True)

    _, emoji, label, default = meta
    current = await db.get_setting(f"link:{key}") or default

    await state.set_state(LinkEditState.waiting_url)
    await state.update_data(link_key=key, link_label=label, link_default=default)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔄 Сбросить к дефолту", callback_data=f"adm:link_reset:{key}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:links")],
    ])
    await cb.message.answer(
        f"✏️ Редактирование: <b>{emoji} {label}</b>\n\n"
        f"Текущая ссылка:\n<code>{current}</code>\n\n"
        f"Введите новую ссылку (должна начинаться с https://):",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(LinkEditState.waiting_url, F.text)
async def adm_link_edit_save(message: Message, db: Database, state: FSMContext):
    data = await state.get_data()
    key = data.get("link_key")
    label = data.get("link_label")

    if not key:
        await state.clear()
        return

    url = message.text.strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        return await message.answer("❌ Ссылка должна начинаться с <code>https://</code>. Попробуйте ещё раз:", parse_mode="HTML")

    await db.set_setting(f"link:{key}", url)
    await state.clear()

    await message.answer(
        f"✅ Ссылка <b>{label}</b> обновлена!\n\n<code>{url}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К ссылкам", callback_data="adm:links")]
        ])
    )


@router.callback_query(F.data.startswith("adm:link_reset:"))
async def adm_link_reset(cb: CallbackQuery, db: Database, state: FSMContext):
    key = cb.data.split(":")[2]
    meta = next((l for l in DESIGN_LINKS if l[0] == key), None)
    if not meta:
        return await cb.answer("Ссылка не найдена", show_alert=True)

    _, emoji, label, default = meta
    await db.set_setting(f"link:{key}", default)
    await state.clear()

    await cb.message.answer(
        f"🔄 Ссылка <b>{emoji} {label}</b> сброшена к дефолту:\n<code>{default}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К ссылкам", callback_data="adm:links")]
        ])
    )
    await cb.answer("✅ Сброшено!")


# ═══════════════════════════════════════════════════════════════════════════
# 📢  АВТОПОСТИНГ ОБНОВЛЕНИЙ В КАНАЛ
# ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:autopost")
async def adm_autopost_menu(cb: CallbackQuery, db: Database, config=None):
    enabled = await db.get_setting("autopost:enabled") != "0"
    channel = await db.get_setting("autopost:channel_id") or (str(config.update_channel_id) if config else "-1004437922263")
    status_emoji = "🟢 Включен" if enabled else "🔴 Выключен"
    toggle_text = "🔴 Выключить" if enabled else "🟢 Включить"

    text = (
        "📢 <b>Управление автопостингом обновлений в канал</b>\n\n"
        f"Статус: <b>{status_emoji}</b>\n"
        f"Канал для постов: <code>{channel}</code>\n\n"
        "<i>При добавлении нового товара бот автоматически отправляет красивый пост с фото, описанием, ценой и кнопкой быстрой покупки в этот канал!</i>"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{toggle_text} автопостинг", callback_data="adm:autopost_toggle")],
        [InlineKeyboardButton(text="✏️ Изменить канал", callback_data="adm:autopost_set_channel")],
        [InlineKeyboardButton(text="🚀 Отправить тестовый пост", callback_data="adm:autopost_test")],
        [InlineKeyboardButton(text="⬅️ Админ-меню", callback_data="adm:menu")]
    ])
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:autopost_toggle")
async def adm_autopost_toggle(cb: CallbackQuery, db: Database, config=None):
    current = await db.get_setting("autopost:enabled") != "0"
    new_val = "0" if current else "1"
    await db.set_setting("autopost:enabled", new_val)
    status_str = "включен" if new_val == "1" else "выключен"
    await cb.answer(f"Автопостинг {status_str}!")
    await adm_autopost_menu(cb, db, config)


@router.callback_query(F.data == "adm:autopost_set_channel")
async def adm_autopost_set_channel(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AutopostChannelState.waiting_channel)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:autopost")]
    ])
    await cb.message.answer(
        "✏️ Отправьте <b>ID канала</b> (например: <code>-1004437922263</code>) или <b>юзернейм канала</b> (например: <code>@my_channel</code>):\n\n"
        "<i>⚠️ Убедитесь, что бот добавлен администратором в этот канал с правом публикации сообщений!</i>",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await cb.answer()


@router.message(AutopostChannelState.waiting_channel, F.text)
async def adm_autopost_channel_save(message: Message, db: Database, state: FSMContext):
    ch = message.text.strip()
    if not ch:
        return await message.answer("❌ Введите ID или юзернейм канала:")

    await db.set_setting("autopost:channel_id", ch)
    await state.clear()
    await message.answer(f"✅ Канал автопостинга сохранён: <code>{ch}</code>", parse_mode="HTML", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm:autopost_test")
async def adm_autopost_test(cb: CallbackQuery, bot: Bot, db: Database, config=None):
    # Ищем любой последний активный товар для теста
    cur = await db.conn.execute("SELECT id FROM products WHERE visible = 1 ORDER BY id DESC LIMIT 1")
    row = await cur.fetchone()
    if not row:
        return await cb.answer("В магазине нет активных товаров для теста", show_alert=True)

    from autopost import send_product_autopost
    ok = await send_product_autopost(bot, db, row["id"], config)
    if ok:
        await cb.answer("✅ Тестовый пост успешно отправлен в канал!", show_alert=True)
    else:
        await cb.answer("❌ Ошибка отправки! Проверьте, что бот админ в канале и ID указан верно.", show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════
# 🌴  РЕКЛАМА И БРОНИ (ADS ADMIN)
# ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:ads")
async def adm_ads_menu(cb: CallbackQuery, db: Database):
    ads = await db.list_all_ads(limit=30)
    lines = ["🌴 <b>Заказы рекламы и рассылок</b>\n"]
    rows = []
    if not ads:
        lines.append("<i>Пока нет активных заявок или броней рекламы.</i>")
    else:
        for ad in ads:
            atype = ad["ad_type"]
            status = "🟢" if ad["status"] == "active" else ("🟡" if ad["status"] == "pending" else "⚪")
            if atype == "mailing":
                lines.append(f"{status} 📨 <b>Рассылка #{ad['id']}:</b> {ad['slot_date']} {ad['slot_time']} (от @{ad['username'] or ad['user_id']}) — {texts.fmt_usd(ad['price_cents'])}")
            elif atype == "button":
                lines.append(f"{status} 🔘 <b>Кнопка #{ad['id']}:</b> «{ad['button_title']}» ({ad['days']} дн., до {ad['expires_at']})")
            elif atype == "welcome":
                lines.append(f"{status} 👋 <b>Приветствие #{ad['id']}:</b> ({ad['days']} дн., до {ad['expires_at']})")
            rows.append([InlineKeyboardButton(text=f"🗑 Удалить слот #{ad['id']} ({ad['ad_type']})", callback_data=f"adm:ad_del:{ad['id']}")])

    rows.append([InlineKeyboardButton(text="⬅️ Админ-меню", callback_data="adm:menu")])
    text = "\n".join(lines)
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await cb.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await cb.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:ad_del:"))
async def adm_ad_del(cb: CallbackQuery, db: Database):
    slot_id = int(cb.data.split(":")[2])
    await db.delete_ad_slot(slot_id)
    await cb.answer("Рекламный слот удалён!")
    await adm_ads_menu(cb, db)


# ─────────────────────────────────────────────────────────────
# 🏷 УПРАВЛЕНИЕ ЦЕНАМИ И СКИДКАМИ (%)
# ─────────────────────────────────────────────────────────────

class AdminPricingState(StatesGroup):
    waiting_for_percent = State()
    waiting_for_confirm = State()


def pricing_main_kb(total_count: int, discounted_count: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🌍 На ВСЕ товары сразу", callback_data="adm:price_scope:all")],
        [InlineKeyboardButton(text="📁 По разделам (категориям)", callback_data="adm:price_scope:cats")],
        [InlineKeyboardButton(text="📦 По отдельному товару", callback_data="adm:price_scope:prods")],
    ]
    if discounted_count > 0:
        rows.append([InlineKeyboardButton(text=f"🔄 Сбросить ВСЕ скидки ({discounted_count})", callback_data="adm:price_reset_all_confirm")])
    rows.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def percent_choice_kb(operation: str) -> InlineKeyboardMarkup:
    if operation == "discount":
        rows = [
            [InlineKeyboardButton(text="-5%", callback_data="adm:price_val:5"),
             InlineKeyboardButton(text="-10%", callback_data="adm:price_val:10"),
             InlineKeyboardButton(text="-15%", callback_data="adm:price_val:15")],
            [InlineKeyboardButton(text="-20%", callback_data="adm:price_val:20"),
             InlineKeyboardButton(text="-25%", callback_data="adm:price_val:25"),
             InlineKeyboardButton(text="-30%", callback_data="adm:price_val:30")],
            [InlineKeyboardButton(text="-40%", callback_data="adm:price_val:40"),
             InlineKeyboardButton(text="-50%", callback_data="adm:price_val:50"),
             InlineKeyboardButton(text="-70%", callback_data="adm:price_val:70")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="adm:pricing")]
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="+5%", callback_data="adm:price_val:5"),
             InlineKeyboardButton(text="+10%", callback_data="adm:price_val:10"),
             InlineKeyboardButton(text="+15%", callback_data="adm:price_val:15")],
            [InlineKeyboardButton(text="+20%", callback_data="adm:price_val:20"),
             InlineKeyboardButton(text="+25%", callback_data="adm:price_val:25"),
             InlineKeyboardButton(text="+30%", callback_data="adm:price_val:30")],
            [InlineKeyboardButton(text="+40%", callback_data="adm:price_val:40"),
             InlineKeyboardButton(text="+50%", callback_data="adm:price_val:50"),
             InlineKeyboardButton(text="+100%", callback_data="adm:price_val:100")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="adm:pricing")]
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:pricing")
async def adm_pricing_menu(cb: CallbackQuery, state: FSMContext, db: Database):
    """Главный экран управления скидками и наценками."""
    await state.clear()
    stats = await db.get_pricing_summary()
    text = (
        "🏷 <b>УПРАВЛЕНИЕ ЦЕНАМИ И СКИДКАМИ (%)</b>\n\n"
        f"📊 <b>Текущее состояние магазина:</b>\n"
        f"• Всего товаров: <b>{stats['total_count']} шт.</b>\n"
        f"• Товаров с активной скидкой: <b>{stats['discounted_count']} шт.</b>\n\n"
        "<i>Выберите, как применить скидку или повышение цены:</i>"
    )
    await cb.message.answer(text, reply_markup=pricing_main_kb(stats['total_count'], stats['discounted_count']), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:price_scope:all")
async def adm_price_scope_all(cb: CallbackQuery, state: FSMContext, db: Database):
    """Выбор операции для ВСЕХ товаров сразу."""
    await state.clear()
    stats = await db.get_pricing_summary()
    text = (
        "🌍 <b>Изменение цен на ВСЕ ТОВАРЫ ШОПА</b>\n\n"
        f"📦 Всего товаров под изменение: <b>{stats['total_count']} шт.</b>\n"
        f"🏷 Активных скидок сейчас: <b>{stats['discounted_count']} шт.</b>\n\n"
        "<i>Выберите действие для всех товаров сразу:</i>"
    )
    rows = [
        [InlineKeyboardButton(text="📉 Скидка на ВСЕ товары (%)", callback_data="adm:price_op:all:0:discount")],
        [InlineKeyboardButton(text="📈 Повысить ВСЕ товары (%)", callback_data="adm:price_op:all:0:markup")],
    ]
    if stats['discounted_count'] > 0:
        rows.append([InlineKeyboardButton(text="🔄 Сбросить скидки на всех товарах", callback_data="adm:price_reset_all_confirm")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:pricing")])
    await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:price_scope:cats")
async def adm_price_scope_cats(cb: CallbackQuery, db: Database):
    """Выбор раздела для массового изменения."""
    cats = await db.list_categories()
    if not cats:
        return await cb.answer("В магазине нет категорий", show_alert=True)
    rows = [[InlineKeyboardButton(text=f"📁 {c['name']}", callback_data=f"adm:price_cat:{c['id']}")] for c in cats]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:pricing")])
    await cb.message.answer("📁 <b>Выберите раздел для изменения цен:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:price_cat:"))
async def adm_price_cat_chosen(cb: CallbackQuery, db: Database):
    """Выбор операции для конкретного раздела."""
    cat_id = int(cb.data.split(":")[2])
    cat = await db.get_category(cat_id)
    if not cat:
        return await cb.answer("Раздел не найден", show_alert=True)
    stats = await db.get_pricing_summary(category_id=cat_id)
    text = (
        f"📁 <b>Раздел «{cat['name']}»</b>\n\n"
        f"📦 Товаров в этом разделе: <b>{stats['total_count']} шт.</b>\n"
        f"🏷 Активных скидок в разделе: <b>{stats['discounted_count']} шт.</b>\n\n"
        "<i>Выберите действие для всех товаров раздела:</i>"
    )
    rows = [
        [InlineKeyboardButton(text="📉 Скидка на раздел (%)", callback_data=f"adm:price_op:cat:{cat_id}:discount")],
        [InlineKeyboardButton(text="📈 Повысить раздел (%)", callback_data=f"adm:price_op:cat:{cat_id}:markup")],
    ]
    if stats['discounted_count'] > 0:
        rows.append([InlineKeyboardButton(text="🔄 Сбросить скидки в разделе", callback_data=f"adm:price_reset:cat:{cat_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ К разделам", callback_data="adm:price_scope:cats")])
    await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:price_scope:prods")
async def adm_price_scope_prods(cb: CallbackQuery, db: Database):
    """Выбор категории для поиска отдельного товара."""
    cats = await db.list_categories()
    if not cats:
        return await cb.answer("В магазине нет категорий", show_alert=True)
    rows = [[InlineKeyboardButton(text=f"📁 {c['name']}", callback_data=f"adm:price_cat_prods:{c['id']}")] for c in cats]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:pricing")])
    await cb.message.answer("📦 <b>Выберите раздел товара:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:price_cat_prods:"))
async def adm_price_cat_prods(cb: CallbackQuery, db: Database):
    """Список товаров категории для изменения цены конкретного товара."""
    cat_id = int(cb.data.split(":")[2])
    prods = await db.list_products(cat_id, visible_only=False)
    if not prods:
        return await cb.answer("В разделе нет товаров", show_alert=True)
    rows = []
    for p in prods:
        disc_badge = " 🔥" if ("old_price" in p.keys() and p["old_price"] and p["old_price"] > p["price"]) else ""
        rows.append([InlineKeyboardButton(
            text=f"{p['name']} — {texts.fmt_usd(p['price'])}{disc_badge}",
            callback_data=f"adm:price_prod_menu:{p['id']}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ К разделам", callback_data="adm:price_scope:prods")])
    await cb.message.answer("📦 <b>Выберите товар для изменения цены (%):</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:price_prod_menu:"))
async def adm_price_prod_menu(cb: CallbackQuery, db: Database):
    """Меню управления ценой одного конкретного товара."""
    pid = int(cb.data.split(":")[2])
    p = await db.get_product(pid)
    if not p:
        return await cb.answer("Товар не найден", show_alert=True)
    
    if "old_price" in p.keys() and p.get("old_price") and p["old_price"] > p["price"]:
        disc_pct = int(round((1 - p["price"] / p["old_price"]) * 100))
        price_line = f"💵 Цена: <s>{texts.fmt_usd(p['old_price'])}</s> <b>{texts.fmt_usd(p['price'])}</b> 🔥 (-{disc_pct}%)"
        has_disc = True
    else:
        price_line = f"💵 Цена: <b>{texts.fmt_usd(p['price'])}</b>"
        has_disc = False

    text = (
        f"📦 <b>Товар: {p['name']}</b>\n\n"
        f"{price_line}\n\n"
        "<i>Выберите операцию над ценой этого товара:</i>"
    )
    rows = [
        [InlineKeyboardButton(text="📉 Скидка на товар (%)", callback_data=f"adm:price_op:prod:{pid}:discount")],
        [InlineKeyboardButton(text="📈 Повысить цену товара (%)", callback_data=f"adm:price_op:prod:{pid}:markup")],
    ]
    if has_disc:
        rows.append([InlineKeyboardButton(text="🔄 Сбросить скидку (вернуть старую цену)", callback_data=f"adm:price_reset:prod:{pid}")])
    rows.append([InlineKeyboardButton(text="⬅️ К списку товаров", callback_data=f"adm:price_cat_prods:{p['category_id']}")])
    await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:price_op:"))
async def adm_price_op_start(cb: CallbackQuery, state: FSMContext, db: Database):
    """Запуск ввода процента для скидки или повышения."""
    parts = cb.data.split(":")
    scope = parts[2]       # all | cat | prod
    target_id = int(parts[3])
    op = parts[4]          # discount | markup

    await state.clear()
    await state.update_data(scope=scope, target_id=target_id, op=op)
    await state.set_state(AdminPricingState.waiting_for_percent)

    if scope == "all":
        target_title = "ВСЕ товары магазина"
    elif scope == "cat":
        cat = await db.get_category(target_id)
        target_title = f"раздел «{cat['name']}»" if cat else "раздел"
    else:
        prod = await db.get_product(target_id)
        target_title = f"товар «{prod['name']}»" if prod else "товар"

    await state.update_data(target_title=target_title)

    if op == "discount":
        text = (
            f"📉 <b>Установка скидки в %</b>\n"
            f"Область применения: <b>{target_title}</b>\n\n"
            "Выберите процент скидки на клавиатуре или <b>отправьте число сообщением</b> (от 1 до 99):"
        )
    else:
        text = (
            f"📈 <b>Повышение цен (наценка в %)</b>\n"
            f"Область применения: <b>{target_title}</b>\n\n"
            "Выберите процент повышения на клавиатуре или <b>отправьте число сообщением</b> (например 10, 25, 50):"
        )

    await cb.message.answer(text, reply_markup=percent_choice_kb(op), parse_mode="HTML")
    await cb.answer()


@router.callback_query(AdminPricingState.waiting_for_percent, F.data.startswith("adm:price_val:"))
async def adm_price_val_button(cb: CallbackQuery, state: FSMContext, db: Database):
    """Выбор процента быстрой кнопкой."""
    pct_val = float(cb.data.split(":")[2])
    await _handle_percent_selected(cb.message, pct_val, state, db)
    await cb.answer()


@router.message(AdminPricingState.waiting_for_percent, F.text)
async def adm_price_val_text(message: Message, state: FSMContext, db: Database):
    """Ввод процента числом в чат."""
    raw = message.text.strip().replace("%", "").replace(",", ".").replace("+", "").replace("-", "")
    try:
        val = float(raw)
        if val <= 0:
            return await message.answer("⚠️ Процент должен быть положительным числом больше 0. Попробуйте снова:")
        data = await state.get_data()
        if data.get("op") == "discount" and val >= 100:
            return await message.answer("⚠️ Скидка не может быть 100% или больше. Введите число от 1 до 99:")
    except ValueError:
        return await message.answer("⚠️ Введите число (например: <code>15</code> или <code>20</code>):", parse_mode="HTML")

    await _handle_percent_selected(message, val, state, db)


async def _handle_percent_selected(target_msg: Message, percent: float, state: FSMContext, db: Database):
    """Генерация экрана подтверждения с предпросмотром пересчёта цен."""
    data = await state.get_data()
    scope = data.get("scope", "all")
    target_id = data.get("target_id", 0)
    op = data.get("op", "discount")
    target_title = data.get("target_title", "Товары")

    await state.update_data(percent=percent)
    await state.set_state(AdminPricingState.waiting_for_confirm)

    op_name = f"Скидка <b>-{percent:g}%</b>" if op == "discount" else f"Повышение цены <b>+{percent:g}%</b>"

    pid = target_id if scope == "prod" else None
    cid = target_id if scope == "cat" else None
    stats = await db.get_pricing_summary(product_id=pid, category_id=cid)
    samples = stats.get("sample_products", [])

    preview_lines = []
    for p in samples:
        cur_p = p["price"]
        prev_old = p.get("old_price")
        base_p = prev_old if (op == "discount" and prev_old is not None and prev_old > cur_p) else cur_p
        if op == "discount":
            new_p = max(1, int(round(base_p * (1.0 - percent / 100.0))))
        else:
            new_p = max(1, int(round(cur_p * (1.0 + percent / 100.0))))
        preview_lines.append(f"• {p['name'][:30]}: {texts.fmt_usd(cur_p)} ➡️ <b>{texts.fmt_usd(new_p)}</b>")

    preview_text = "\n".join(preview_lines) if preview_lines else "• Нет товаров для пересчёта"

    confirm_text = (
        f"⚠️ <b>ПОДТВЕРЖДЕНИЕ ИЗМЕНЕНИЯ ЦЕН</b>\n\n"
        f"• <b>Объект:</b> {target_title} (товаров: <b>{stats['total_count']} шт.</b>)\n"
        f"• <b>Операция:</b> {op_name}\n\n"
        f"📋 <b>Пример пересчёта цен:</b>\n"
        f"{preview_text}\n\n"
        f"❓ <b>Применить изменения прямо сейчас?</b>"
    )
    rows = [
        [InlineKeyboardButton(text="✅ Да, применить", callback_data="adm:price_confirm"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="adm:pricing")]
    ]
    await target_msg.answer(confirm_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


@router.callback_query(AdminPricingState.waiting_for_confirm, F.data == "adm:price_confirm")
async def adm_price_confirm_exec(cb: CallbackQuery, state: FSMContext, db: Database):
    """Применение изменений цен в базе данных."""
    data = await state.get_data()
    scope = data.get("scope", "all")
    target_id = data.get("target_id", 0)
    op = data.get("op", "discount")
    percent = float(data.get("percent", 0))
    target_title = data.get("target_title", "Товары")
    await state.clear()

    pid = target_id if scope == "prod" else None
    cid = target_id if scope == "cat" else None

    if op == "discount":
        count, updated = await db.apply_discount(percent=percent, product_id=pid, category_id=cid)
        action_desc = f"Скидка <b>-{percent:g}%</b> успешно применена!"
    else:
        count, updated = await db.apply_markup(percent=percent, product_id=pid, category_id=cid)
        action_desc = f"Повышение цен на <b>+{percent:g}%</b> успешно применено!"

    samples_text = "\n".join([f"• {u['name'][:30]}: {texts.fmt_usd(u['old_price'])} ➡️ <b>{texts.fmt_usd(u['new_price'])}</b>" for u in updated[:4]])

    res_text = (
        f"✅ <b>Цены успешно обновлены!</b>\n\n"
        f"• Затронуто: <b>{count} товаров</b> ({target_title})\n"
        f"• {action_desc}\n\n"
        f"📋 <b>Примеры обновлённых цен:</b>\n"
        f"{samples_text}"
    )
    rows = [
        [InlineKeyboardButton(text="🏷 В управление ценами", callback_data="adm:pricing")],
        [InlineKeyboardButton(text="📦 К товарам", callback_data="adm:prods")],
        [InlineKeyboardButton(text="⬅️ В админ-меню", callback_data="adm:menu")]
    ]
    await cb.message.answer(res_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


# ── Сброс скидок ──

@router.callback_query(F.data == "adm:price_reset_all_confirm")
async def adm_price_reset_all_confirm(cb: CallbackQuery, db: Database):
    """Подтверждение сброса всех скидок магазина."""
    stats = await db.get_pricing_summary()
    text = (
        f"⚠️ <b>Сброс ВСЕХ скидок магазина</b>\n\n"
        f"Товаров с активными скидками: <b>{stats['discounted_count']} шт.</b>\n\n"
        f"Всем товарам со скидкой будут возвращены их исходные базовые цены.\n\n"
        f"Вы уверены?"
    )
    rows = [
        [InlineKeyboardButton(text="✅ Да, сбросить все скидки", callback_data="adm:price_reset_all_exec")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:pricing")]
    ]
    await cb.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "adm:price_reset_all_exec")
async def adm_price_reset_all_exec(cb: CallbackQuery, db: Database):
    """Выполнение сброса всех скидок."""
    count = await db.reset_discounts()
    await cb.message.answer(
        f"✅ <b>Скидки сброшены!</b>\n\nВосстановлены исходные цены для <b>{count} товаров</b>.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏷 В управление ценами", callback_data="adm:pricing")],
            [InlineKeyboardButton(text="⬅️ В админ-меню", callback_data="adm:menu")]
        ]),
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:price_reset:cat:"))
async def adm_price_reset_cat(cb: CallbackQuery, db: Database):
    """Сброс скидок в конкретном разделе."""
    cat_id = int(cb.data.split(":")[3])
    count = await db.reset_discounts(category_id=cat_id)
    await cb.message.answer(
        f"✅ <b>Скидки в разделе сброшены!</b>\n\nВосстановлены исходные цены для <b>{count} товаров</b>.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📁 К разделам", callback_data="adm:price_scope:cats")],
            [InlineKeyboardButton(text="🏷 В управление ценами", callback_data="adm:pricing")]
        ]),
        parse_mode="HTML"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:price_reset:prod:"))
async def adm_price_reset_prod(cb: CallbackQuery, db: Database):
    """Сброс скидки на одном товаре."""
    pid = int(cb.data.split(":")[3])
    count = await db.reset_discounts(product_id=pid)
    p = await db.get_product(pid)
    name = p["name"] if p else f"#{pid}"
    cur_p = texts.fmt_usd(p["price"]) if p else ""
    await cb.message.answer(
        f"✅ <b>Скидка на товар «{name}» сброшена!</b>\n\nВосстановлена базовая цена: <b>{cur_p}</b>.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 К товару", callback_data=f"adm:prod:{pid}")],
            [InlineKeyboardButton(text="🏷 В управление ценами", callback_data="adm:pricing")]
        ]),
        parse_mode="HTML"
    )
    await cb.answer()







