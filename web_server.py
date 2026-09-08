import asyncio
import hashlib
import hmac
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import aiohttp
from aiohttp import web

# Гарантируем, что текущая директория в sys.path
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from config import load_config
from db import Database
from payments import Payments, apply_paid_invoice, accrue_referral
import texts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("web_server")

config = load_config()
db_path = os.getenv("DB_PATH", str(BASE_DIR / "shop.db"))
db = Database(db_path)
payments: Payments | None = None

def get_payments() -> Payments:
    global payments
    if payments is None:
        payments = Payments(config.cryptopay_token, config.cryptopay_testnet, config.xrocket_api_key)
    return payments

# Настройки для TON / Tonkeeper
TON_WALLET_ADDRESS = os.getenv("TON_WALLET_ADDRESS", "").strip() or "UQDFu-8iB6e7M3qN5J_kU7T2Y4v1Xz9P8O0W-aBcDeFgHiJk"
TON_USD_RATE = float(os.getenv("TON_USD_RATE", "5.50"))  # Ориентировочный курс TON к USD

# Хранилище сессий в памяти (token -> user_id)
SESSIONS: dict[str, dict] = {}
# Временное хранилище инвойсов Tonkeeper (topup_id -> dict)
TONKEEPER_ORDERS: dict[str, dict] = {}


def generate_session_token(user_id: int) -> str:
    salt = uuid.uuid4().hex
    secret = config.bot_token.encode()
    data = f"{user_id}:{salt}:{time.time()}".encode()
    sig = hmac.new(secret, data, hashlib.sha256).hexdigest()
    token = f"{user_id}_{salt}_{sig[:16]}"
    SESSIONS[token] = {"user_id": user_id, "created_at": time.time()}
    return token


def get_user_id_from_request(request: web.Request) -> int | None:
    # 1. Из Cookie
    token = request.cookies.get("session_token")
    # 2. Из заголовка Authorization
    if not token and "Authorization" in request.headers:
        auth_header = request.headers["Authorization"]
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if token and token in SESSIONS:
        return SESSIONS[token]["user_id"]
    return None


def verify_telegram_auth(auth_data: dict, bot_token: str) -> bool:
    """Проверка подписи данных от Telegram Login Widget по спецификации Telegram."""
    check_hash = auth_data.get("hash")
    if not check_hash:
        return False

    data_check_arr = []
    for k, v in sorted(auth_data.items()):
        if k != "hash" and v is not None and v != "":
            data_check_arr.append(f"{k}={v}")
    data_check_string = "\n".join(data_check_arr)

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated_hash, check_hash)


async def send_channel_log(text: str) -> bool:
    """Отправка логов покупок и пополнений с сайта напрямую в канал логов через Telegram Bot API."""
    if not config.bot_token or not config.admin_group_id:
        return False
    url = f"https://api.telegram.org/bot{config.bot_token}/sendMessage"
    payload = {
        "chat_id": config.admin_group_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    logger.info("Уведомление успешно отправлено в группу логов.")
                    return True
                else:
                    body = await resp.text()
                    logger.warning(f"Ошибка отправки в канал логов: {resp.status} {body}")
                    return False
    except Exception as e:
        logger.warning(f"Не удалось отправить лог в канал: {e}")
        return False


# ==========================================
# API HANDLERS
# ==========================================

async def handle_init(request: web.Request):
    """Инициализационные параметры для фронтенда."""
    shop_title = await db.get_setting("shop_title") or "GLOCK SHOP"
    support_url = await db.get_setting("link:support_url") or "https://t.me/glock_admin_bot"
    wallet_addr = await db.get_setting("ton:wallet_address") or TON_WALLET_ADDRESS

    user_id = get_user_id_from_request(request)
    user_info = None
    if user_id:
        user = await db.get_user(user_id)
        if user:
            stats = await db.get_user_stats(user_id)
            loyalty = texts.get_loyalty_info(stats["total_spent_cents"])
            user_info = {
                "id": user["id"],
                "username": user["username"],
                "balance_cents": user["balance"],
                "balance_usd": f"${user['balance'] / 100:.2f}",
                "balance_rub": texts.fmt_balance(user["balance"], "RUB"),
                "loyalty": loyalty,
            }

    return web.json_response({
        "shop_title": shop_title,
        "bot_username": config.bot_username,
        "exchange_rate": texts.EXCHANGE_RATE,
        "support_url": support_url,
        "ton_wallet": wallet_addr,
        "user": user_info,
    })


async def handle_catalog(request: web.Request):
    """Возвращает категории и товары со всеми фотографиями и ценами."""
    try:
        cur = await db.conn.execute("SELECT id, name, description, position FROM categories ORDER BY position, id")
        categories = [dict(r) for r in await cur.fetchall()]

        cur = await db.conn.execute(
            "SELECT id, category_id, name, description, price, old_price, kind, content_type, visible "
            "FROM products WHERE visible = 1 ORDER BY id"
        )
        products_raw = [dict(r) for r in await cur.fetchall()]

        # Добавляем фотографии и форматирование цен к товарам
        products = []
        for p in products_raw:
            cur = await db.conn.execute(
                "SELECT file_id FROM product_photos WHERE product_id = ? ORDER BY position",
                (p["id"],)
            )
            photo_rows = await cur.fetchall()
            photos = []
            for pr in photo_rows:
                fid = pr["file_id"]
                if fid.startswith("photos/"):
                    photos.append(f"/{fid}")
                elif fid.startswith("file_id:"):
                    photos.append(f"/api/photo/{fid[8:]}")
                else:
                    photos.append(f"/api/photo/{fid}")

            # Если фото нет — проверяем глобальный баннер или дефолт
            if not photos:
                photos.append("/static/img/product_placeholder.png")

            price_cents = p["price"]
            old_price_cents = p.get("old_price")
            discount_pct = 0
            if old_price_cents and old_price_cents > price_cents:
                discount_pct = int(round((1 - price_cents / old_price_cents) * 100))

            # Проверяем наличие (stock)
            if p["kind"] == "oneoff":
                cur = await db.conn.execute(
                    "SELECT COUNT(*) FROM product_items WHERE product_id = ? AND status = 'free'",
                    (p["id"],)
                )
                cnt = (await cur.fetchone())[0]
                in_stock = cnt > 0
                stock_count = cnt
            else:
                in_stock = True
                stock_count = 999

            p["photos"] = photos
            p["price_cents"] = price_cents
            p["price_usd"] = f"${price_cents / 100:.2f}"
            p["price_rub"] = f"{int(round(price_cents * texts.EXCHANGE_RATE / 100)):,} ₽".replace(",", " ")
            p["old_price_usd"] = f"${old_price_cents / 100:.2f}" if old_price_cents else None
            p["discount_pct"] = discount_pct
            p["in_stock"] = in_stock
            p["stock_count"] = stock_count
            products.append(p)

        return web.json_response({"categories": categories, "products": products})
    except Exception as e:
        logger.exception("Ошибка в /api/catalog")
        return web.json_response({"error": str(e)}, status=500)


async def handle_product_detail(request: web.Request):
    """Детальная карточка товара по ID."""
    prod_id = int(request.match_info["id"])
    prod = await db.get_product(prod_id)
    if not prod or not prod["visible"]:
        return web.json_response({"error": "Товар не найден"}, status=404)

    cur = await db.conn.execute(
        "SELECT file_id FROM product_photos WHERE product_id = ? ORDER BY position", (prod_id,)
    )
    photo_rows = await cur.fetchall()
    photos = [f"/{r[0]}" if r[0].startswith("photos/") else f"/api/photo/{r[0]}" for r in photo_rows]
    if not photos:
        photos = ["/static/img/product_placeholder.png"]

    p_dict = dict(prod)
    p_dict["photos"] = photos
    p_dict["price_usd"] = f"${prod['price'] / 100:.2f}"
    p_dict["price_rub"] = f"{int(round(prod['price'] * texts.EXCHANGE_RATE / 100)):,} ₽".replace(",", " ")

    return web.json_response(p_dict)


# ==========================================
# AUTH & PROFILE
# ==========================================

async def handle_auth_telegram(request: web.Request):
    """Авторизация через Telegram Login Widget."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Неверный формат JSON"}, status=400)

    # Верификация подписи
    is_valid = verify_telegram_auth(data, config.bot_token)
    if not is_valid:
        logger.warning(f"Неудачная проверка хеша Telegram Login: {data}")
        return web.json_response({"error": "Неверная подпись данных Telegram"}, status=401)

    user_id = int(data["id"])
    username = data.get("username")
    first_name = data.get("first_name", "")
    photo_url = data.get("photo_url", "")

    # Проверяем или создаем пользователя в общей БД
    user = await db.get_or_create_user(user_id, username)

    # Привязка реферера, если передан ref и у пользователя еще нет реферера
    referrer_id = data.get("referrer_id")
    if referrer_id and not user["referrer_id"]:
        try:
            ref_id_int = int(referrer_id)
            if ref_id_int != user_id:
                ref_user = await db.get_user(ref_id_int)
                if ref_user:
                    await db.conn.execute("UPDATE users SET referrer_id = ? WHERE id = ?", (ref_id_int, user_id))
                    await db.conn.commit()
                    logger.info(f"Пользователь {user_id} привязан к рефереру {ref_id_int}")
        except Exception as e:
            logger.warning(f"Ошибка привязки реферера: {e}")

    # Создаем сессию
    token = generate_session_token(user_id)
    SESSIONS[token]["username"] = username
    SESSIONS[token]["first_name"] = first_name
    SESSIONS[token]["photo_url"] = photo_url

    response = web.json_response({
        "status": "ok",
        "token": token,
        "user": {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "photo_url": photo_url,
            "balance_cents": user["balance"],
            "balance_usd": f"${user['balance'] / 100:.2f}",
            "balance_rub": texts.fmt_balance(user["balance"], "RUB"),
        }
    })
    # Ставим Cookie
    response.set_cookie("session_token", token, max_age=86400 * 30, httponly=False, samesite="Lax")
    return response


async def handle_auth_demo(request: web.Request):
    """Тестовый/демо вход по ID для локальной разработки или тестирования без виджета."""
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
    except Exception:
        return web.json_response({"error": "Укажите user_id"}, status=400)

    if not user_id:
        # Берем первого пользователя из базы для демо
        cur = await db.conn.execute("SELECT id, username FROM users ORDER BY id LIMIT 1")
        row = await cur.fetchone()
        if row:
            user_id = row[0]
        else:
            user_id = 999999999

    user = await db.get_or_create_user(user_id, f"user_{user_id}")
    token = generate_session_token(user_id)
    response = web.json_response({
        "status": "ok",
        "token": token,
        "user": {
            "id": user_id,
            "username": user["username"],
            "balance_cents": user["balance"],
            "balance_usd": f"${user['balance'] / 100:.2f}",
            "balance_rub": texts.fmt_balance(user["balance"], "RUB"),
        }
    })
    response.set_cookie("session_token", token, max_age=86400 * 30, httponly=False, samesite="Lax")
    return response


async def handle_auth_logout(request: web.Request):
    token = request.cookies.get("session_token")
    if token and token in SESSIONS:
        del SESSIONS[token]
    response = web.json_response({"status": "ok"})
    response.del_cookie("session_token")
    return response


async def handle_user_me(request: web.Request):
    """Возвращает актуальный профиль, баланс, скидки и реферальную ссылку."""
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Не авторизован"}, status=401)

    user = await db.get_user(user_id)
    if not user:
        return web.json_response({"error": "Пользователь не найден"}, status=404)

    stats = await db.get_user_stats(user_id)
    loyalty = texts.get_loyalty_info(stats["total_spent_cents"])
    invited_cnt = await db.count_invited(user_id)
    clients_cnt = await db.count_referral_clients(user_id)
    earned_cents = await db.total_referral_earned(user_id)
    ref_percent = texts.percent_for_clients(clients_cnt) if hasattr(texts, "percent_for_clients") else 10

    # Реферальная ссылка на сам сайт
    host = request.headers.get("Host", "localhost:8000")
    scheme = request.headers.get("X-Forwarded-Proto", "http")
    site_ref_url = f"{scheme}://{host}/?ref={user_id}"

    # Последние покупки
    cur = await db.conn.execute(
        "SELECT id, product_name, price, method, content_type, content_value, created_at "
        "FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 20",
        (user_id,)
    )
    purchases = [dict(r) for r in await cur.fetchall()]
    for p in purchases:
        p["price_usd"] = f"${p['price'] / 100:.2f}"
        p["price_rub"] = f"{int(round(p['price'] * texts.EXCHANGE_RATE / 100)):,} ₽".replace(",", " ")

    return web.json_response({
        "id": user["id"],
        "username": user["username"],
        "balance_cents": user["balance"],
        "balance_usd": f"${user['balance'] / 100:.2f}",
        "balance_rub": texts.fmt_balance(user["balance"], "RUB"),
        "total_spent_usd": f"${stats['total_spent_cents'] / 100:.2f}",
        "completed_orders": stats["completed_orders"],
        "loyalty": loyalty,
        "referral": {
            "link": site_ref_url,
            "invited_count": invited_cnt,
            "clients_count": clients_cnt,
            "earned_usd": f"${earned_cents / 100:.2f}",
            "percent": ref_percent,
        },
        "purchases": purchases,
    })


# ==========================================
# PAYMENTS & PURCHASES
# ==========================================

async def handle_buy_balance(request: web.Request):
    """Покупка товара с баланса."""
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Авторизуйтесь для покупки"}, status=401)

    try:
        data = await request.json()
        prod_id = int(data.get("product_id", 0))
    except Exception:
        return web.json_response({"error": "Неверный запрос"}, status=400)

    user = await db.get_user(user_id)
    prod = await db.get_product(prod_id)
    if not prod:
        return web.json_response({"error": "Товар не найден"}, status=404)

    # Применяем личную скидку лояльности, если есть
    stats = await db.get_user_stats(user_id)
    loyalty = texts.get_loyalty_info(stats["total_spent_cents"])
    discount_p = loyalty["percent"]
    final_price = prod["price"]
    if discount_p > 0:
        final_price = int(round(prod["price"] * (100 - discount_p) / 100))

    if user["balance"] < final_price:
        needed = final_price - user["balance"]
        return web.json_response({
            "error": "no_funds",
            "message": f"Недостаточно средств на балансе. Пополните баланс на ${needed / 100:.2f}",
            "needed_cents": needed,
        }, status=400)

    # Проводим покупку через БД
    result = await db.buy_with_balance(user_id, prod_id)
    status = result.get("status")

    if status == "no_funds":
        return web.json_response({"error": "no_funds", "message": "Недостаточно средств"}, status=400)
    elif status in ("gone", "out_of_stock"):
        return web.json_response({"error": "out_of_stock", "message": "Товар закончился"}, status=400)
    elif status == "ok":
        # Отправляем лог в Telegram канал
        u_name = user["username"]
        mention = f"@{u_name}" if u_name else f"ID: {user_id}"
        log_text = (
            f"🌐 <b>Новая покупка на САЙТЕ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 Товар: <b>{result['name']}</b>\n"
            f"💵 Сумма: <b>${result['price'] / 100:.2f}</b> ({int(round(result['price'] * texts.EXCHANGE_RATE / 100)):,} ₽)\n"
            f"💳 Способ: <b>Баланс</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 Покупатель: {mention}\n"
            f"🆔 ID: <code>{user_id}</code>"
        )
        asyncio.create_task(send_channel_log(log_text))

        # Начисляем реферальный бонус
        asyncio.create_task(accrue_referral(db, user_id, result["price"], "site_balance_purchase"))

        return web.json_response({
            "status": "ok",
            "message": "Покупка успешно выполнена!",
            "purchase_id": result["purchase_id"],
            "name": result["name"],
            "content_type": result.get("content_type"),
            "content_value": result.get("content_value"),
        })

    return web.json_response({"error": "Не удалось завершить покупку"}, status=500)


async def handle_cryptobot_create(request: web.Request):
    """Создание счета CryptoBot для пополнения или прямой покупки."""
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Авторизуйтесь для пополнения"}, status=401)

    try:
        data = await request.json()
        amount_usd = float(data.get("amount_usd", 0))
    except Exception:
        return web.json_response({"error": "Неверный формат суммы"}, status=400)

    if amount_usd < 0.1:
        return web.json_response({"error": "Минимальная сумма $0.10"}, status=400)

    amount_cents = int(round(amount_usd * 100))
    desc = f"Пополнение баланса на сайте (ID: {user_id})"

    try:
        p = get_payments()
        invoice_id, pay_url = await p.create_invoice(amount_cents, desc, provider="cryptopay")
        # Сохраняем счет в БД
        await db.create_invoice(invoice_id, user_id, "topup", None, None, amount_cents, pay_url)
        return web.json_response({
            "status": "ok",
            "invoice_id": invoice_id,
            "pay_url": pay_url,
            "amount_usd": f"${amount_usd:.2f}",
        })
    except Exception as e:
        logger.exception("Ошибка создания счета в CryptoBot")
        return web.json_response({"error": f"Ошибка CryptoBot: {str(e)}"}, status=500)


async def handle_cryptobot_status(request: web.Request):
    """Проверка статуса счета в CryptoBot."""
    user_id = get_user_id_from_request(request)
    invoice_id = int(request.match_info["invoice_id"])

    inv = await db.get_invoice(invoice_id)
    if not inv:
        return web.json_response({"error": "Счет не найден"}, status=404)

    if inv["status"] == "paid":
        return web.json_response({"status": "paid", "message": "Счет уже оплачен"})

    # Запрашиваем статус в CryptoPay API
    p = get_payments()
    statuses = await p.get_statuses([invoice_id])
    st = statuses.get(invoice_id, "active")

    if st == "paid":
        result = await apply_paid_invoice(db, inv)
        if result:
            user = await db.get_user(inv["user_id"])
            u_name = user["username"] if user else None
            mention = f"@{u_name}" if u_name else f"ID: {inv['user_id']}"
            topup_text = (
                f"💳 <b>Пополнение баланса на САЙТЕ!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 Сумма: <b>${inv['amount'] / 100:.2f}</b>\n"
                f"💳 Способ: <b>CryptoBot</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 Пользователь: {mention}\n"
                f"🆔 ID: <code>{inv['user_id']}</code>"
            )
            asyncio.create_task(send_channel_log(topup_text))

        return web.json_response({"status": "paid", "message": "Оплата успешно получена! Баланс пополнен."})
    elif st == "expired":
        await db.mark_invoice_expired(invoice_id)
        return web.json_response({"status": "expired", "message": "Срок действия счета истек"})
    else:
        return web.json_response({"status": "active", "message": "Ожидание оплаты..."})


async def handle_tonkeeper_create(request: web.Request):
    """Генерация данных для оплаты через Tonkeeper."""
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Авторизуйтесь для пополнения"}, status=401)

    try:
        data = await request.json()
        amount_usd = float(data.get("amount_usd", 0))
    except Exception:
        return web.json_response({"error": "Неверный формат суммы"}, status=400)

    if amount_usd < 0.1:
        return web.json_response({"error": "Минимальная сумма $0.10"}, status=400)

    amount_cents = int(round(amount_usd * 100))
    wallet_addr = await db.get_setting("ton:wallet_address") or TON_WALLET_ADDRESS
    amount_ton = round(amount_usd / TON_USD_RATE, 2)
    if amount_ton <= 0:
        amount_ton = 0.05
    nanotons = int(amount_ton * 1_000_000_000)

    topup_id = f"TK_{user_id}_{int(time.time())}"
    comment = topup_id

    # Tonkeeper universal link и deep link
    universal_link = f"https://app.tonkeeper.com/transfer/{wallet_addr}?amount={nanotons}&text={quote(comment)}"
    deep_link = f"ton://transfer/{wallet_addr}?amount={nanotons}&text={quote(comment)}"

    TONKEEPER_ORDERS[topup_id] = {
        "user_id": user_id,
        "amount_usd": amount_usd,
        "amount_cents": amount_cents,
        "amount_ton": amount_ton,
        "nanotons": nanotons,
        "comment": comment,
        "wallet": wallet_addr,
        "status": "pending",
        "created_at": time.time(),
    }

    return web.json_response({
        "status": "ok",
        "topup_id": topup_id,
        "wallet": wallet_addr,
        "amount_usd": f"${amount_usd:.2f}",
        "amount_ton": amount_ton,
        "comment": comment,
        "universal_link": universal_link,
        "deep_link": deep_link,
    })


async def handle_tonkeeper_check(request: web.Request):
    """Проверка платежа Tonkeeper по комментарию через публичный TON API."""
    user_id = get_user_id_from_request(request)
    try:
        data = await request.json()
        topup_id = data.get("topup_id")
    except Exception:
        return web.json_response({"error": "Неверный запрос"}, status=400)

    order = TONKEEPER_ORDERS.get(topup_id)
    if not order:
        return web.json_response({"error": "Заказ не найден"}, status=404)

    if order["status"] == "paid":
        return web.json_response({"status": "paid", "message": "Платеж уже подтвержден!"})

    wallet = order["wallet"]
    expected_comment = order["comment"]
    paid = False

    # Запрашиваем публичный API Toncenter для поиска транзакции с нужным комментарием
    try:
        api_url = f"https://toncenter.com/api/v2/getTransactions?address={wallet}&limit=20"
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    t_data = await resp.json()
                    if t_data.get("ok") and t_data.get("result"):
                        for tx in t_data["result"]:
                            in_msg = tx.get("in_msg", {})
                            msg_comment = in_msg.get("message", "")
                            val = int(in_msg.get("value", 0))
                            if expected_comment in msg_comment and val >= (order["nanotons"] * 0.95):
                                paid = True
                                break
    except Exception as e:
        logger.warning(f"Ошибка проверки Toncenter API: {e}")

    if paid:
        order["status"] = "paid"
        await db.add_balance(order["user_id"], order["amount_cents"])
        user = await db.get_user(order["user_id"])
        u_name = user["username"] if user else None
        mention = f"@{u_name}" if u_name else f"ID: {order['user_id']}"
        topup_text = (
            f"💎 <b>Пополнение баланса через Tonkeeper на САЙТЕ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💵 Сумма: <b>${order['amount_usd']:.2f}</b> (~{order['amount_ton']} TON)\n"
            f"💳 Способ: <b>Tonkeeper</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 Пользователь: {mention}\n"
            f"🆔 ID: <code>{order['user_id']}</code>"
        )
        asyncio.create_task(send_channel_log(topup_text))
        asyncio.create_task(accrue_referral(db, order["user_id"], order["amount_cents"], "site_tonkeeper_topup"))
        return web.json_response({"status": "paid", "message": "Платеж найден! Баланс успешно пополнен."})
    else:
        return web.json_response({
            "status": "pending",
            "message": "Платеж еще не обнаружен в сети TON. Подождите 1-2 минуты после перевода в Tonkeeper."
        })


async def handle_photo_proxy(request: web.Request):
    """Проксирование или отдача фото, если это file_id."""
    file_id = request.match_info["file_id"]
    # Проверяем локальный файл
    local_path = BASE_DIR / "photos" / file_id
    if local_path.exists():
        return web.FileResponse(local_path)

    # Если это Telegram file_id — запрашиваем через getFile
    if config.bot_token:
        try:
            get_file_url = f"https://api.telegram.org/bot{config.bot_token}/getFile?file_id={file_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(get_file_url) as resp:
                    if resp.status == 200:
                        f_info = await resp.json()
                        if f_info.get("ok"):
                            file_path = f_info["result"]["file_path"]
                            dl_url = f"https://api.telegram.org/file/bot{config.bot_token}/{file_path}"
                            async with session.get(dl_url) as dl_resp:
                                if dl_resp.status == 200:
                                    img_data = await dl_resp.read()
                                    return web.Response(body=img_data, content_type="image/jpeg")
        except Exception as e:
            logger.warning(f"Ошибка загрузки file_id {file_id}: {e}")

    # Fallback на placeholder
    ph = BASE_DIR / "web" / "img" / "product_placeholder.png"
    if ph.exists():
        return web.FileResponse(ph)
    return web.Response(status=404)


async def handle_index(request: web.Request):
    """Отдает главную страницу сайта."""
    index_file = BASE_DIR / "web" / "index.html"
    return web.FileResponse(index_file)


# ==========================================
# APPLICATION SETUP
# ==========================================

async def on_startup(app: web.Application):
    await db.connect()
    try:
        get_payments()
    except Exception as e:
        logger.warning(f"Инициализация платежного шлюза отложена: {e}")
    logger.info("Подключение к shop.db успешно установлено.")


async def on_cleanup(app: web.Application):
    global payments
    if payments:
        try:
            await payments.close()
        except Exception:
            pass
    await db.close()
    logger.info("Соединения базы данных и платежей закрыты.")


def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # API маршруты
    app.router.add_get("/api/init", handle_init)
    app.router.add_get("/api/catalog", handle_catalog)
    app.router.add_get("/api/product/{id}", handle_product_detail)

    # Авторизация
    app.router.add_post("/api/auth/telegram", handle_auth_telegram)
    app.router.add_post("/api/auth/test_login", handle_auth_demo)
    app.router.add_post("/api/auth/logout", handle_auth_logout)
    app.router.add_get("/api/user/me", handle_user_me)

    # Покупки и пополнения
    app.router.add_post("/api/buy/balance", handle_buy_balance)
    app.router.add_post("/api/pay/cryptobot/create", handle_cryptobot_create)
    app.router.add_get("/api/pay/cryptobot/status/{invoice_id}", handle_cryptobot_status)
    app.router.add_post("/api/pay/tonkeeper/create", handle_tonkeeper_create)
    app.router.add_post("/api/pay/tonkeeper/check", handle_tonkeeper_check)
    app.router.add_get("/api/photo/{file_id}", handle_photo_proxy)

    # Статические файлы
    photos_dir = BASE_DIR / "photos"
    photos_dir.mkdir(exist_ok=True)
    app.router.add_static("/photos/", path=str(photos_dir), name="photos")

    web_dir = BASE_DIR / "web"
    web_dir.mkdir(exist_ok=True)
    app.router.add_static("/static/", path=str(web_dir), name="static")

    # Главная страница
    app.router.add_get("/", handle_index)

    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Запуск веб-сайта магазина на http://localhost:{port}")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)
