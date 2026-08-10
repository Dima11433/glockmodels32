import uuid
from aiogram import Router, F
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


@router.callback_query(F.data == "activate_promo_btn")
async def start_promo_activation_cb(call: CallbackQuery, state: FSMContext):
    await start_promo_activation(call.message, state)
    await call.answer()


@router.message(F.text == "🎫 Промокод")
async def start_promo_activation(message: Message, state: FSMContext):
    await state.set_state(PromoState.waiting_for_code)
    await message.answer("🔑 Введите промокод для активации:")


@router.message(PromoState.waiting_for_code)
async def process_promo_code(message: Message, state: FSMContext, db: Database):
    await state.clear()
    code = message.text.strip()
    res = await db.activate_promocode(message.from_user.id, code)
    if res["status"] == "not_found":
        await message.answer("❌ Промокод не найден или неактивен.")
    elif res["status"] == "limit_reached":
        await message.answer("❌ Закончились активации у данного промокода.")
    elif res["status"] == "already_used":
        await message.answer("❌ Вы уже активировали этот промокод!")
    elif res["status"] == "ok":
        if res["reward_type"] == "bonus":
            await message.answer(f"🎉 Промокод успешно активирован!\n💰 Вам зачислено: +{res['value']} ₽")
        else:
            await message.answer(f"🎉 Промокод активирован! Скидка {res['value']}% при покупке.")


@router.callback_query(F.data == "create_check_btn")
async def start_create_check_cb(call: CallbackQuery, state: FSMContext, db: Database):
    # Use the callback user (who pressed the button), not the original message author
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
async def process_check_amount(message: Message, state: FSMContext, db: Database, bot):
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
        [InlineKeyboardButton(text="🎁 Передать чек другу", url=f"https://t.me/share/url?url={check_link}&text=Держи%20подарочный%20чек%20на%20{amount}%20рублей!")]
    ])
    await message.answer(
        f"✅ **Чек успешно создан!**\n\n"
        f"💵 Сумма: **{amount} ₽**\n"
        f"🔗 Ссылка активации: `{check_link}`\n\n"
        f"Передайте эту ссылку другу. Любой пользователь сможет забрать эти деньги на свой баланс!",
        parse_mode="Markdown",
        reply_markup=markup
    )


async def handle_check_start(message: Message, code: str, db: Database):
    res = await db.claim_check(message.from_user.id, code)
    if res["status"] == "not_found":
        await message.answer("❌ Чек не найден.")
    elif res["status"] == "already_claimed":
        await message.answer("❌ Этот чек уже был активирован ранее.")
    elif res["status"] == "ok":
        await message.answer(f"🎉 Вы успешно активировали чек!\n💰 На ваш баланс зачислено **+{res['amount']} ₽**", parse_mode="Markdown")
