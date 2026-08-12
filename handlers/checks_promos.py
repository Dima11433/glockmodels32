import uuid
from aiogram import Bot, Router, F
from aiogram.filters import CommandObject, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db import Database

router = Router()


class CheckState(StatesGroup):
    waiting_for_amount = State()


class PromoState(StatesGroup):
    waiting_for_code = State()


async def _notify_admin_promo(bot: Bot, db: Database, res: dict, config=None) -> None:
    """Отправляет уведомление в админ-группу об активации промокода."""
    user_id = res.get("user_id")
    username = res.get("username")
    code = res.get("code", "?")
    reward_type = res.get("reward_type", "bonus")
    value = res.get("value", 0)

    user_link = f"tg://user?id={user_id}"
    user_mention = f'<a href="{user_link}">@{username}</a>' if username else f'<a href="{user_link}">#{user_id}</a>'

    reward_text = f"+{value} ₽ на баланс" if reward_type == "bonus" else f"Скидка {value}%"

    text = (
        f"🎫 <b>Промокод активирован!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Код: <code>{code}</code>\n"
        f"🎁 Награда: {reward_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Пользователь: {user_mention}\n"
        f"🆔 ID: <code>{user_id}</code>"
    )

    # Отправляем в группу логов
    if config and getattr(config, "admin_group_id", None):
        try:
            await bot.send_message(config.admin_group_id, text, parse_mode="HTML")
        except Exception:
            pass

    # Также в личку админу
    admin_id = await db.get_setting("admin_id")
    if admin_id:
        try:
            await bot.send_message(int(admin_id), text, parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data == "activate_promo_btn")
async def start_promo_activation_cb(call: CallbackQuery, state: FSMContext):
    await state.set_state(PromoState.waiting_for_code)
    await call.message.answer("🔑 Введите промокод для активации:")
    await call.answer()


@router.message(F.text == "🎫 Промокод")
async def start_promo_activation(message: Message, state: FSMContext):
    await state.set_state(PromoState.waiting_for_code)
    await message.answer("🔑 Введите промокод для активации:")


@router.message(PromoState.waiting_for_code)
async def process_promo_code(message: Message, state: FSMContext, db: Database, bot: Bot, config=None):
    await state.clear()
    code = message.text.strip()
    res = await db.activate_promocode(message.from_user.id, code)

    if res["status"] == "not_found":
        await message.answer("❌ Промокод не найден или неактивен.")
    elif res["status"] == "limit_reached":
        await message.answer("❌ Промокод закончился — все активации использованы.")
    elif res["status"] == "already_used":
        await message.answer("❌ Вы уже использовали этот промокод максимальное количество раз.")
    elif res["status"] == "ok":
        if res["reward_type"] == "bonus":
            await message.answer(
                f"🎉 Промокод успешно активирован!\n"
                f"💰 На ваш баланс зачислено: <b>+{res['value']} ₽</b>",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"🎉 Промокод активирован!\n"
                f"🏷 Скидка <b>{res['value']}%</b> при следующей покупке.",
                parse_mode="HTML"
            )
        # Уведомляем администратора
        await _notify_admin_promo(bot, db, res, config)


@router.callback_query(F.data == "create_check_btn")
async def start_create_check_cb(call: CallbackQuery, state: FSMContext, db: Database):
    user = await db.get_user(call.from_user.id)
    balance = user["balance"] if user else 0
    if balance <= 0:
        await call.message.answer("❌ У вас нулевой баланс! Пополните баланс или оформите покупку.")
        await call.answer()
        return
    await state.set_state(CheckState.waiting_for_amount)
    await call.message.answer(f"💰 Ваш баланс: {balance} ₽\n\nУкажите сумму чека, которую вы хотите передать другу:")
    await call.answer()


@router.message(F.text == "💸 Создать чек")
async def start_create_check(message: Message, state: FSMContext, db: Database):
    user = await db.get_user(message.from_user.id)
    balance = user["balance"] if user else 0
    if balance <= 0:
        await message.answer("❌ У вас нулевой баланс! Пополните баланс или оформите покупку.")
        return
    await state.set_state(CheckState.waiting_for_amount)
    await message.answer(f"💰 Ваш баланс: {balance} ₽\n\nУкажите сумму чека, которую вы хотите передать другу:")


@router.message(CheckState.waiting_for_amount)
async def process_check_amount(message: Message, state: FSMContext, db: Database, bot: Bot):
    await state.clear()
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ Введите корректное положительное число.")
        return
    amount = int(message.text)
    code = f"chk_{uuid.uuid4().hex[:10]}"
    ok = await db.create_check(message.from_user.id, amount, code)
    if not ok:
        await message.answer("❌ Недостаточно средств на балансе!")
        return

    bot_user = await bot.get_me()
    check_link = f"https://t.me/{bot_user.username}?start={code}"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎁 Передать чек другу",
            url=f"https://t.me/share/url?url={check_link}&text=Держи%20подарочный%20чек%20на%20{amount}%20рублей!"
        )]
    ])
    await message.answer(
        f"✅ <b>Чек успешно создан!</b>\n\n"
        f"💵 Сумма: <b>{amount} ₽</b>\n"
        f"🔗 Ссылка: <code>{check_link}</code>\n\n"
        f"Передайте эту ссылку другу. Любой пользователь сможет забрать деньги на свой баланс!",
        parse_mode="HTML",
        reply_markup=markup
    )


async def handle_check_start(message: Message, code: str, db: Database):
    res = await db.claim_check(message.from_user.id, code)
    if res["status"] == "not_found":
        await message.answer("❌ Чек не найден.")
    elif res["status"] == "already_claimed":
        await message.answer("❌ Этот чек уже был активирован ранее.")
    elif res["status"] == "ok":
        await message.answer(
            f"🎉 Вы успешно активировали чек!\n"
            f"💰 На ваш баланс зачислено: <b>+{res['amount']} ₽</b>",
            parse_mode="HTML"
        )
