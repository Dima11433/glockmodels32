from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from db import Database
import texts


def menu_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:main")]


async def main_menu(db: Database | None = None) -> InlineKeyboardMarkup:
    """Главное меню с кнопками основных функций."""
    async def g(key: str, default: str) -> str:
        if db:
            v = await db.get_setting(f"btn:{key}")
            return v or default
        return default

    s_search = await g("search", texts.BTN_SEARCH)
    s_catalog = await g("catalog", texts.BTN_CATALOG)
    s_profile = await g("profile", texts.BTN_PROFILE)
    s_support = await g("support", texts.BTN_SUPPORT)
    s_ads = await g("ads", "🌴 Реклама")
    s_more = await g("more", "⚙️ Ещё")

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s_search, callback_data="menu:search"),
         InlineKeyboardButton(text=s_catalog, callback_data="menu:catalog")],
        [InlineKeyboardButton(text=s_profile, callback_data="menu:profile"),
         InlineKeyboardButton(text=s_support, callback_data="menu:support")],
        [InlineKeyboardButton(text=s_more, callback_data="menu:more")],
    ])


def pagination_keyboard(current_page: int, total_pages: int, callback_prefix: str) -> InlineKeyboardMarkup:
    """Create pagination controls."""
    buttons = []
    
    # Previous button
    if current_page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"{callback_prefix}:{current_page - 1}"))
    else:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data="noop"))
    
    # Page indicator
    buttons.append(InlineKeyboardButton(text=f"{current_page + 1}/{total_pages}", callback_data="noop"))
    
    # Next button
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"{callback_prefix}:{current_page + 1}"))
    else:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data="noop"))
    
    return InlineKeyboardMarkup(inline_keyboard=[buttons, [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:main")]])


# List of main menu buttons (suffix, title) used for design customization
MAIN_BUTTONS = [
    ("search", texts.BTN_SEARCH),
    ("catalog", texts.BTN_CATALOG),
    ("profile", texts.BTN_PROFILE),
    ("support", texts.BTN_SUPPORT),
    ("ads", "💎 Реклама"),
    ("history", texts.BTN_HISTORY),
    ("referral", texts.BTN_REFERRAL),
    ("about", "💎 О Магазине"),
    ("reviews", "💎 Отзывы"),
    ("create_check", "💎 Создать чек"),
    ("promocode", "💎 Промокод"),
    ("more", "💎 Ещё"),
]

ITEMS_PER_PAGE = 6
