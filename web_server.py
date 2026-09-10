import asyncio
import hashlib
import hmac
import json
import logging
import os
import shutil
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
from payments import Payments, apply_paid_invoice, accrue_referral, percent_for_clients
import texts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("web_server")

config = load_config()
db_path = os.getenv("DB_PATH", str(BASE_DIR / "shop.db"))

# Инициализация БД из seed-файла, если база отсутствует (на хостинге)
if not os.path.exists(db_path) and os.path.exists(BASE_DIR / "shop_seed.db"):
    try:
        shutil.copy2(BASE_DIR / "shop_seed.db", db_path)
        logger.info(f"База данных успешно инициализирована из shop_seed.db в {db_path}")
    except Exception as e:
        logger.warning(f"Ошибка копирования seed базы: {e}")

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

# Хранилище сессий (token -> {user_id, username, created_at})
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


async def save_session_db(token: str, user_id: int, username: str):
    """Сохраняет сессию в память и в постоянную таблицу SQLite site_sessions."""
    now = time.time()
    SESSIONS[token] = {"user_id": user_id, "username": username, "created_at": now}
    try:
        await db.conn.execute(
            "INSERT OR REPLACE INTO site_sessions (token, user_id, username, created_at) VALUES (?, ?, ?, ?)",
            (token, user_id, username, now)
        )
        await db.conn.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения сессии в БД: {e}")


def get_token_from_request(request: web.Request) -> str | None:
    """Извлекает токен авторизации из Authorization header, query-параметров или Cookie."""
    # 1. Заголовок Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    # 2. Query param ?session_token=... или ?token=...
    if "session_token" in request.query:
        return request.query["session_token"].strip()
    if "token" in request.query:
        return request.query["token"].strip()
    # 3. Cookie session_token
    token = request.cookies.get("session_token")
    if token:
        return token.strip()
    return None


async def get_user_id_from_request(request: web.Request) -> int | None:
    token = get_token_from_request(request)
    if not token:
        return None
    if token in SESSIONS:
        return SESSIONS[token]["user_id"]
    try:
        cur = await db.conn.execute(
            "SELECT user_id, username, created_at FROM site_sessions WHERE token = ?",
            (token,)
        )
        row = await cur.fetchone()
        if row:
            SESSIONS[token] = {"user_id": row[0], "username": row[1], "created_at": row[2]}
            return row[0]
    except Exception:
        pass
    return None


async def get_user_from_request(request: web.Request) -> dict | None:
    """Извлекает объект пользователя из БД по токену сессии."""
    token = get_token_from_request(request)
    if not token:
        return None
    user_id = None
    if token in SESSIONS:
        user_id = SESSIONS[token].get("user_id")
    else:
        try:
            cur = await db.conn.execute(
                "SELECT user_id, username, created_at FROM site_sessions WHERE token = ?",
                (token,)
            )
            row = await cur.fetchone()
            if row:
                user_id = row[0]
                SESSIONS[token] = {"user_id": user_id, "username": row[1], "created_at": row[2]}
        except Exception:
            pass
    if not user_id:
        return None
    user = await db.get_user(user_id)
    return dict(user) if user else None


async def check_is_admin(user_id: int | None, username: str | None) -> bool:
    """Проверяет права администратора по никнейму, настройкам и таблице admins."""
    if not user_id and not username:
        return False
    if username and config.admin_username:
        if username.lower().lstrip("@") == config.admin_username.lower().lstrip("@"):
            return True
    try:
        admin_id_setting = await db.get_setting("admin_id")
        if admin_id_setting and user_id and str(user_id) == str(admin_id_setting):
            return True
    except Exception:
        pass
    try:
        return await db.is_admin(user_id=user_id, username=username)
    except Exception:
        return False


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

    user_id = await get_user_id_from_request(request)
    user_info = None
    if user_id:
        user = await db.get_user(user_id)
        if user:
            stats = await db.get_user_stats(user_id)
            loyalty = texts.get_loyalty_info(stats["total_spent_cents"])
            is_adm = await check_is_admin(user["id"], user["username"])
            user_info = {
                "id": user["id"],
                "username": user["username"],
                "balance_cents": user["balance"],
                "balance_usd": f"${user['balance'] / 100:.2f}",
                "balance_rub": texts.fmt_balance(user["balance"], "RUB"),
                "loyalty": loyalty,
                "is_admin": is_adm,
            }

    tunnel_url = ""
    if (BASE_DIR / "tunnel_url.txt").exists():
        try:
            tunnel_url = (BASE_DIR / "tunnel_url.txt").read_text(encoding="utf-8").strip()
        except Exception:
            pass

    return web.json_response({
        "shop_title": shop_title,
        "bot_username": config.bot_username,
        "exchange_rate": texts.EXCHANGE_RATE,
        "support_url": support_url,
        "ton_wallet": wallet_addr,
        "api_url": tunnel_url,
        "user": user_info,
    })


async def handle_catalog(request: web.Request):
    """Возвращает категории и товары со всеми фотографиями и ценами."""
    try:
        cur = await db.conn.execute("SELECT id, name, description, position, parent_id FROM categories ORDER BY position, id")
        categories = [dict(r) for r in await cur.fetchall()]
        cat_map = {c["id"]: c for c in categories}

        cur = await db.conn.execute(
            "SELECT id, category_id, name, description, price, old_price, kind, content_type, visible "
            "FROM products WHERE visible = 1 ORDER BY id"
        )
        products_raw = [dict(r) for r in await cur.fetchall()]

        # Пакетная загрузка фото для всех товаров за 1 быстрый запрос
        cur = await db.conn.execute(
            "SELECT product_id, file_id FROM product_photos ORDER BY product_id, position"
        )
        photos_by_product: dict[int, list[str]] = {}
        for r in await cur.fetchall():
            pid = r[0]
            fid = r[1]
            if fid.startswith("photos/"):
                p_url = f"/{fid}"
            elif fid.startswith("file_id:"):
                p_url = f"/api/photo/{fid[8:]}"
            else:
                p_url = f"/api/photo/{fid}"
            photos_by_product.setdefault(pid, []).append(p_url)

        # Пакетная загрузка свободных единиц товаров за 1 быстрый запрос
        cur = await db.conn.execute(
            "SELECT product_id, COUNT(*) FROM product_items WHERE status = 'free' GROUP BY product_id"
        )
        stock_by_product = {r[0]: r[1] for r in await cur.fetchall()}

        # Формирование итогового списка товаров
        products = []
        for p in products_raw:
            photos = photos_by_product.get(p["id"], [])
            if not photos:
                photos = ["/static/img/product_placeholder.png"]

            price_cents = p["price"]
            old_price_cents = p.get("old_price")
            discount_pct = 0
            if old_price_cents and old_price_cents > price_cents:
                discount_pct = int(round((1 - price_cents / old_price_cents) * 100))

            if p["kind"] == "oneoff":
                cnt = stock_by_product.get(p["id"], 0)
                in_stock = cnt > 0
                stock_count = cnt
            else:
                in_stock = True
                stock_count = 999

            cat_info = cat_map.get(p["category_id"], {})
            p["category_name"] = cat_info.get("name", "")
            p["parent_category_id"] = cat_info.get("parent_id")
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
    await save_session_db(token, user_id, username)
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


async def handle_auth_identifier(request: web.Request):
    """Вход по @username или Telegram ID с поддержкой всех пользователей бота."""
    try:
        data = await request.json()
        raw_ident = str(data.get("identifier", "")).strip()
    except Exception:
        return web.json_response({"error": "Укажите username или Telegram ID"}, status=400)

    if not raw_ident:
        return web.json_response({"error": "Введите @username или Telegram ID"}, status=400)

    ident = raw_ident.lstrip("@").strip()
    user_row = None

    if ident.isdigit():
        cur = await db.conn.execute("SELECT id, username, balance FROM users WHERE id = ?", (int(ident),))
        user_row = await cur.fetchone()

    if not user_row:
        cur = await db.conn.execute("SELECT id, username, balance FROM users WHERE LOWER(username) = LOWER(?)", (ident,))
        user_row = await cur.fetchone()

    if user_row:
        user_id = user_row[0]
        username = user_row[1]
    else:
        if ident.isdigit():
            user_id = int(ident)
            username = f"user_{user_id}"
        else:
            user_id = int(hashlib.md5(ident.encode()).hexdigest()[:8], 16) % 900000000 + 100000000
            username = ident
        await db.get_or_create_user(user_id, username)

    user = await db.get_user(user_id)

    # Привязка реферера
    ref_id = data.get("referrer_id")
    if ref_id and not user["referrer_id"]:
        try:
            r_int = int(ref_id)
            if r_int != user_id:
                await db.conn.execute("UPDATE users SET referrer_id = ? WHERE id = ?", (r_int, user_id))
                await db.conn.commit()
        except Exception:
            pass

    token = generate_session_token(user_id)
    await save_session_db(token, user_id, user["username"])
    SESSIONS[token]["username"] = user["username"]

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


async def send_telegram_direct_message(chat_id: int, text: str) -> bool:
    """Прямая отправка сообщения через Telegram Bot API без запущенного bot.py."""
    url = f"https://api.telegram.org/bot{config.bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json()
                return bool(data.get("ok"))
    except Exception as e:
        logger.error(f"Ошибка отправки Telegram сообщения: {e}")
        return False


async def handle_auth_send_code(request: web.Request):
    """Генерирует 6-значный код и отправляет его пользователю в Telegram."""
    try:
        data = await request.json()
        raw_ident = str(data.get("identifier", "")).strip()
    except Exception:
        return web.json_response({"error": "Укажите username или Telegram ID"}, status=400)

    if not raw_ident:
        return web.json_response({"error": "Введите ваш никнейм или Telegram ID"}, status=400)

    ident = raw_ident.lstrip("@").strip()
    user_row = None

    if ident.isdigit():
        cur = await db.conn.execute("SELECT id, username, balance FROM users WHERE id = ?", (int(ident),))
        user_row = await cur.fetchone()

    if not user_row:
        cur = await db.conn.execute("SELECT id, username, balance FROM users WHERE LOWER(username) = LOWER(?)", (ident,))
        user_row = await cur.fetchone()

    if not user_row:
        if ident.isdigit():
            user_id = int(ident)
            user = await db.get_or_create_user(user_id, f"user_{user_id}")
            user_row = (user["id"], user["username"], user["balance"])
        else:
            bot_name = config.bot_username or "glock_models_bot"
            return web.json_response({
                "error": f"Пользователь @{ident} не найден в базе магазина. Сначала откройте бота @{bot_name} и нажмите /start!"
            }, status=404)

    user_id = user_row[0]
    username = user_row[1] or str(user_id)
    now = time.time()

    # Проверка кулдауна (30 секунд) перед повторной отправкой
    cur = await db.conn.execute("SELECT created_at FROM site_otp_codes WHERE user_id = ?", (user_id,))
    prev_otp = await cur.fetchone()
    if prev_otp and (now - prev_otp[0]) < 30:
        sec_left = int(30 - (now - prev_otp[0]))
        return web.json_response({
            "error": f"Подождите {sec_left} сек. перед повторной отправкой кода"
        }, status=429)

    # 6-значный цифровой код
    import secrets
    otp_code = f"{secrets.randbelow(900000) + 100000}"

    await db.conn.execute("""
        INSERT INTO site_otp_codes (user_id, username, code, created_at, attempts)
        VALUES (?, ?, ?, ?, 0)
        ON CONFLICT(user_id) DO UPDATE SET
            code = excluded.code,
            created_at = excluded.created_at,
            attempts = 0
    """, (user_id, username, otp_code, now))
    await db.conn.commit()

    bot_name = config.bot_username or "glock_models_bot"
    text = (
        "🔐 <b>Код авторизации на сайте GLOCK SHOP:</b>\n\n"
        f"👉 <code>{otp_code}</code> 👈\n\n"
        "⏳ <b>Код действует 5 минут.</b> Введите его на сайте для входа в ваш профиль.\n"
        "⚠️ Если вы не запрашивали вход, просто проигнорируйте это сообщение."
    )
    sent = await send_telegram_direct_message(user_id, text)
    if not sent:
        return web.json_response({
            "error": f"Бот не смог отправить сообщение пользователю @{username}. Убедитесь, что вы не заблокировали @{bot_name} в Telegram, и напишите боту /start!"
        }, status=400)

    return web.json_response({
        "status": "ok",
        "user_id": user_id,
        "username": username,
        "message": f"Код отправлен в Telegram пользователю @{username}"
    })


async def handle_auth_verify_code(request: web.Request):
    """Проверяет введенный 6-значный код и авторизует пользователя."""
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        code = str(data.get("code", "")).strip()
    except Exception:
        return web.json_response({"error": "Некорректные параметры"}, status=400)

    if not user_id or not code:
        return web.json_response({"error": "Введите 6-значный код из Telegram"}, status=400)

    cur = await db.conn.execute("SELECT code, created_at, attempts FROM site_otp_codes WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    if not row:
        return web.json_response({"error": "Код не найден или устарел. Запросите новый код"}, status=400)

    saved_code, created_at, attempts = row
    if time.time() - created_at > 300:
        await db.conn.execute("DELETE FROM site_otp_codes WHERE user_id = ?", (user_id,))
        await db.conn.commit()
        return web.json_response({"error": "Срок действия кода истек (5 минут). Запросите код заново"}, status=400)

    if attempts >= 5:
        await db.conn.execute("DELETE FROM site_otp_codes WHERE user_id = ?", (user_id,))
        await db.conn.commit()
        return web.json_response({"error": "Слишком много неверных попыток. Запросите новый код"}, status=400)

    if saved_code != code:
        await db.conn.execute("UPDATE site_otp_codes SET attempts = attempts + 1 WHERE user_id = ?", (user_id,))
        await db.conn.commit()
        rem = 4 - attempts
        return web.json_response({"error": f"Неверный код подтверждения! Осталось попыток: {max(0, rem)}"}, status=400)

    # Успешная проверка!
    await db.conn.execute("DELETE FROM site_otp_codes WHERE user_id = ?", (user_id,))
    await db.conn.commit()

    user = await db.get_user(user_id)
    if not user:
        user = await db.get_or_create_user(user_id, f"user_{user_id}")

    # Привязка реферала
    ref_id = data.get("referrer_id")
    if ref_id and not user["referrer_id"]:
        try:
            r_int = int(ref_id)
            if r_int != user_id:
                await db.conn.execute("UPDATE users SET referrer_id = ? WHERE id = ?", (r_int, user_id))
                await db.conn.commit()
        except Exception:
            pass

    token = generate_session_token(user_id)
    await save_session_db(token, user_id, user["username"])
    is_adm = await check_is_admin(user_id, user["username"])

    response = web.json_response({
        "status": "ok",
        "token": token,
        "user": {
            "id": user_id,
            "username": user["username"],
            "balance_cents": user["balance"],
            "balance_usd": f"${user['balance'] / 100:.2f}",
            "balance_rub": texts.fmt_balance(user["balance"], "RUB"),
            "is_admin": is_adm,
        }
    })
    response.set_cookie("session_token", token, max_age=86400 * 30, httponly=False, samesite="Lax")
    return response


async def handle_auth_bot_create(request: web.Request):
    """Генерация ссылки для бесшовного входа через Telegram-бота."""
    tok = uuid.uuid4().hex[:12]
    now = time.time()
    await db.conn.execute(
        "INSERT INTO site_auth_tokens (token, status, created_at) VALUES (?, 'pending', ?)",
        (tok, now)
    )
    await db.conn.commit()
    bot_name = config.bot_username or "glock_models_bot"
    bot_url = f"https://t.me/{bot_name}?start=auth_{tok}"
    return web.json_response({
        "status": "ok",
        "token": tok,
        "bot_url": bot_url,
    })


async def handle_auth_bot_poll(request: web.Request):
    """Проверка подтверждения авторизации ботом."""
    tok = request.match_info["token"]
    cur = await db.conn.execute(
        "SELECT user_id, username, first_name, status FROM site_auth_tokens WHERE token = ?",
        (tok,)
    )
    row = await cur.fetchone()
    if not row:
        return web.json_response({"error": "Токен не найден"}, status=404)

    user_id, username, first_name, status = row
    if status != "confirmed" or not user_id:
        return web.json_response({"status": "pending"})

    # Маркируем токен как использованный, предотвращая повторную генерацию сессий
    await db.conn.execute("UPDATE site_auth_tokens SET status = 'consumed' WHERE token = ?", (tok,))
    await db.conn.commit()

    user = await db.get_or_create_user(user_id, username)
    session_token = generate_session_token(user_id)
    await save_session_db(session_token, user_id, username)
    SESSIONS[session_token]["first_name"] = first_name
    is_adm = await check_is_admin(user_id, username)

    response = web.json_response({
        "status": "confirmed",
        "token": session_token,
        "user": {
            "id": user_id,
            "username": user["username"],
            "balance_cents": user["balance"],
            "balance_usd": f"${user['balance'] / 100:.2f}",
            "balance_rub": texts.fmt_balance(user["balance"], "RUB"),
            "is_admin": is_adm,
        }
    })
    response.set_cookie("session_token", session_token, max_age=86400 * 30, httponly=False, samesite="Lax")
    return response


async def handle_auth_demo(request: web.Request):
    """Тестовый/демо вход по ID для локальной разработки или тестирования без виджета."""
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
    except Exception:
        return web.json_response({"error": "Укажите user_id"}, status=400)

    if not user_id:
        cur = await db.conn.execute("SELECT id, username FROM users ORDER BY id LIMIT 1")
        row = await cur.fetchone()
        user_id = row[0] if row else 999999999

    req_username = str(data.get("username", "")).strip().lstrip("@")
    if req_username:
        user = await db.get_or_create_user(user_id, req_username)
        await db.conn.execute("UPDATE users SET username = ? WHERE id = ?", (req_username, user_id))
        await db.conn.commit()
        user = await db.get_user(user_id)
    else:
        user = await db.get_user(user_id)
        if not user:
            user = await db.get_or_create_user(user_id, f"user_{user_id}")
    token = generate_session_token(user_id)
    await save_session_db(token, user_id, user["username"])
    is_adm = await check_is_admin(user_id, user["username"])
    response = web.json_response({
        "status": "ok",
        "token": token,
        "user": {
            "id": user_id,
            "username": user["username"],
            "balance_cents": user["balance"],
            "balance_usd": f"${user['balance'] / 100:.2f}",
            "balance_rub": texts.fmt_balance(user["balance"], "RUB"),
            "is_admin": is_adm,
        }
    })
    response.set_cookie("session_token", token, max_age=86400 * 30, httponly=False, samesite="Lax")
    return response



async def handle_auth_logout(request: web.Request):
    token = get_token_from_request(request)
    if token:
        if token in SESSIONS:
            del SESSIONS[token]
        try:
            await db.conn.execute("DELETE FROM site_sessions WHERE token = ?", (token,))
            await db.conn.commit()
        except Exception:
            pass
    response = web.json_response({"status": "ok"})
    response.del_cookie("session_token")
    return response


async def handle_user_me(request: web.Request):
    """Возвращает актуальный профиль, баланс, скидки и реферальную ссылку."""
    user_id = await get_user_id_from_request(request)
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
    ref_percent = percent_for_clients(clients_cnt)
    is_adm = await check_is_admin(user["id"], user["username"])

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
        "is_admin": is_adm,
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
    user_id = await get_user_id_from_request(request)
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

    # Проводим покупку через БД с учетом персональной скидки
    result = await db.buy_with_balance(user_id, prod_id, final_price=final_price)
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
    user_id = await get_user_id_from_request(request)
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
        await db.create_invoice(
            invoice_id=invoice_id,
            user_id=user_id,
            purpose="topup",
            amount=amount_cents,
            pay_url=pay_url,
            provider="cryptopay",
        )
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
    user_id = await get_user_id_from_request(request)
    try:
        invoice_id = int(request.match_info["invoice_id"])
    except (ValueError, TypeError):
        return web.json_response({"error": "Некорректный ID счета"}, status=400)

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
    user_id = await get_user_id_from_request(request)
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

    now = time.time()
    # Сохраняем заказ в постоянную БД SQLite
    await db.conn.execute("""
        INSERT OR REPLACE INTO site_tonkeeper_orders
        (topup_id, user_id, amount_usd, amount_cents, amount_ton, nanotons, comment, wallet, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (topup_id, user_id, amount_usd, amount_cents, amount_ton, nanotons, comment, wallet_addr, now))
    await db.conn.commit()

    TONKEEPER_ORDERS[topup_id] = {
        "user_id": user_id,
        "amount_usd": amount_usd,
        "amount_cents": amount_cents,
        "amount_ton": amount_ton,
        "nanotons": nanotons,
        "comment": comment,
        "wallet": wallet_addr,
        "status": "pending",
        "created_at": now,
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
    """Проверка платежа Tonkeeper по комментарию через публичный TON API с TonAPI fallback."""
    user_id = await get_user_id_from_request(request)
    try:
        data = await request.json()
        topup_id = data.get("topup_id")
    except Exception:
        return web.json_response({"error": "Неверный запрос"}, status=400)

    # Ищем заказ в БД или памяти
    order = TONKEEPER_ORDERS.get(topup_id)
    if not order:
        cur = await db.conn.execute(
            "SELECT topup_id, user_id, amount_usd, amount_cents, amount_ton, nanotons, comment, wallet, status, created_at FROM site_tonkeeper_orders WHERE topup_id = ?",
            (topup_id,)
        )
        row = await cur.fetchone()
        if not row:
            return web.json_response({"error": "Заказ не найден"}, status=404)
        order = {
            "topup_id": row[0],
            "user_id": row[1],
            "amount_usd": row[2],
            "amount_cents": row[3],
            "amount_ton": row[4],
            "nanotons": row[5],
            "comment": row[6],
            "wallet": row[7],
            "status": row[8],
            "created_at": row[9],
        }
        TONKEEPER_ORDERS[topup_id] = order

    if order["status"] == "paid":
        return web.json_response({"status": "paid", "message": "Платеж уже подтвержден!"})

    wallet = order["wallet"]
    expected_comment = order["comment"]
    paid = False

    # 1. Запрашиваем публичный API Toncenter
    try:
        api_url = f"https://toncenter.com/api/v2/getTransactions?address={wallet}&limit=20"
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
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
        logger.warning(f"Ошибка Toncenter API: {e}")

    # 2. Резервный запрос через TonAPI (если Toncenter недоступен или выдал 429)
    if not paid:
        try:
            tonapi_url = f"https://tonapi.io/v2/blockchain/accounts/{wallet}/transactions?limit=20"
            async with aiohttp.ClientSession() as session:
                async with session.get(tonapi_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        t_data = await resp.json()
                        txs = t_data.get("transactions", [])
                        for tx in txs:
                            in_msg = tx.get("in_msg", {})
                            val = int(in_msg.get("value", 0))
                            decoded = in_msg.get("decoded_body", {})
                            msg_comment = decoded.get("text", "") or in_msg.get("message", "")
                            if expected_comment in msg_comment and val >= (order["nanotons"] * 0.95):
                                paid = True
                                break
        except Exception as e:
            logger.warning(f"Ошибка TonAPI fallback: {e}")

    if paid:
        # Атомарно переводим статус в 'paid' в SQLite
        cur = await db.conn.execute(
            "UPDATE site_tonkeeper_orders SET status = 'paid', paid_at = ? WHERE topup_id = ? AND status = 'pending'",
            (time.time(), topup_id)
        )
        await db.conn.commit()

        if cur.rowcount > 0:
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
    """Проксирование или отдача фото с защитой от directory traversal."""
    file_id = request.match_info["file_id"]
    # Проверяем локальный файл строго внутри папки photos
    photos_dir = (BASE_DIR / "photos").resolve()
    try:
        local_path = (photos_dir / file_id).resolve()
        if photos_dir in local_path.parents and local_path.is_file():
            return web.FileResponse(local_path)
    except Exception:
        pass

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


# ==========================================
# ADMIN PANEL API & CATALOG EXPORT
# ==========================================

async def export_catalog_json() -> bool:
    """Регенерирует статический catalog.json для работы сайта на GitHub Pages."""
    try:
        cur = await db.conn.execute("SELECT id, name, description, position, parent_id FROM categories ORDER BY position, id")
        categories = [dict(r) for r in await cur.fetchall()]
        cat_map = {c["id"]: c for c in categories}

        cur = await db.conn.execute(
            "SELECT id, category_id, name, description, price, old_price, kind, content_type, visible "
            "FROM products WHERE visible = 1 ORDER BY id"
        )
        products_raw = [dict(r) for r in await cur.fetchall()]

        cur = await db.conn.execute("SELECT product_id, file_id FROM product_photos ORDER BY product_id, position")
        photos_by_product: dict[int, list[str]] = {}
        for r in await cur.fetchall():
            pid = r[0]
            fid = r[1]
            if fid.startswith("photos/"):
                p_url = fid
            elif fid.startswith("file_id:"):
                p_url = f"api/photo/{fid[8:]}"
            else:
                p_url = f"api/photo/{fid}"
            photos_by_product.setdefault(pid, []).append(p_url)

        cur = await db.conn.execute(
            "SELECT product_id, COUNT(*) FROM product_items WHERE status = 'free' GROUP BY product_id"
        )
        stock_by_product = {r[0]: r[1] for r in await cur.fetchall()}

        products = []
        for p in products_raw:
            photos = photos_by_product.get(p["id"], [])
            if not photos:
                photos = ["web/img/product_placeholder.png"]

            price_cents = p["price"]
            old_price_cents = p.get("old_price")
            discount_pct = 0
            if old_price_cents and old_price_cents > price_cents:
                discount_pct = int(round((1 - price_cents / old_price_cents) * 100))

            if p["kind"] == "oneoff":
                cnt = stock_by_product.get(p["id"], 0)
                in_stock = cnt > 0
                stock_count = cnt
            else:
                in_stock = True
                stock_count = 999

            cat_info = cat_map.get(p["category_id"], {})
            prod_entry = {
                "id": p["id"],
                "category_id": p["category_id"],
                "name": p["name"],
                "description": p["description"],
                "price": price_cents,
                "old_price": old_price_cents,
                "kind": p["kind"],
                "content_type": p["content_type"],
                "visible": p["visible"],
                "category_name": cat_info.get("name", ""),
                "parent_category_id": cat_info.get("parent_id"),
                "photos": photos,
                "price_cents": price_cents,
                "price_usd": f"${price_cents / 100:.2f}" if price_cents > 0 else "$0",
                "price_rub": f"{int(round(price_cents * texts.EXCHANGE_RATE / 100)):,} ₽".replace(",", " ") if price_cents > 0 else "0 ₽",
                "old_price_usd": f"${old_price_cents / 100:.2f}" if old_price_cents else None,
                "discount_pct": discount_pct,
                "in_stock": in_stock,
                "stock_count": stock_count,
            }
            products.append(prod_entry)

        tunnel_url = ""
        if (BASE_DIR / "tunnel_url.txt").exists():
            try:
                tunnel_url = (BASE_DIR / "tunnel_url.txt").read_text(encoding="utf-8").strip()
            except Exception:
                pass

        data = {
            "shop_title": await db.get_setting("shop_title") or "GLOCK SHOP",
            "support_url": await db.get_setting("link:support_url") or "https://t.me/glock_admin_bot",
            "bot_username": config.bot_username or "glock_models_bot",
            "api_url": tunnel_url,
            "categories": categories,
            "products": products
        }
        with open(BASE_DIR / "catalog.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"catalog.json успешно обновлен ({len(products)} товаров).")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения catalog.json: {e}")
        return False


async def handle_admin_check(request: web.Request):
    """Проверка прав текущего пользователя."""
    user = await get_user_from_request(request)
    if not user:
        return web.json_response({"is_admin": False}, status=401)
    is_adm = await check_is_admin(user["id"], user["username"])
    return web.json_response({"is_admin": is_adm, "username": user["username"], "user_id": user["id"]})


async def handle_admin_products(request: web.Request):
    """Возвращает все товары магазина для админ-панели (включая скрытые)."""
    user = await get_user_from_request(request)
    if not user or not await check_is_admin(user["id"], user["username"]):
        return web.json_response({"error": "Доступ запрещен"}, status=403)

    cur = await db.conn.execute("SELECT id, name, description, position, parent_id FROM categories ORDER BY position, id")
    categories = [dict(r) for r in await cur.fetchall()]
    cat_map = {c["id"]: c for c in categories}

    cur = await db.conn.execute(
        "SELECT id, category_id, name, description, price, old_price, kind, content_type, content_value, visible "
        "FROM products ORDER BY id DESC"
    )
    products_raw = [dict(r) for r in await cur.fetchall()]

    cur = await db.conn.execute("SELECT product_id, file_id FROM product_photos ORDER BY product_id, position")
    photos_by_product: dict[int, list[str]] = {}
    for r in await cur.fetchall():
        pid, fid = r[0], r[1]
        p_url = fid if fid.startswith("photos/") else (f"api/photo/{fid[8:]}" if fid.startswith("file_id:") else f"api/photo/{fid}")
        photos_by_product.setdefault(pid, []).append(p_url)

    cur = await db.conn.execute("SELECT product_id, COUNT(*) FROM product_items WHERE status = 'free' GROUP BY product_id")
    stock_by_product = {r[0]: r[1] for r in await cur.fetchall()}

    products = []
    for p in products_raw:
        photos = photos_by_product.get(p["id"], [])
        if not photos:
            photos = ["web/img/product_placeholder.png"]
        price_cents = p["price"]
        old_price_cents = p.get("old_price")
        discount_pct = 0
        if old_price_cents and old_price_cents > price_cents:
            discount_pct = int(round((1 - price_cents / old_price_cents) * 100))
        cat_info = cat_map.get(p["category_id"], {})
        stock_count = stock_by_product.get(p["id"], 0) if p["kind"] == "oneoff" else 999
        products.append({
            "id": p["id"],
            "category_id": p["category_id"],
            "category_name": cat_info.get("name", "Без раздела"),
            "name": p["name"],
            "description": p["description"],
            "price_cents": price_cents,
            "price_usd": f"${price_cents / 100:.2f}",
            "old_price_cents": old_price_cents,
            "old_price_usd": f"${old_price_cents / 100:.2f}" if old_price_cents else None,
            "discount_pct": discount_pct,
            "kind": p["kind"],
            "content_value": p.get("content_value") or "",
            "visible": p["visible"],
            "stock_count": stock_count,
            "photos": photos
        })

    return web.json_response({"products": products, "categories": categories})


async def handle_admin_product_add(request: web.Request):
    """Добавление нового товара через веб-админку (с поддержкой фото и штучных товаров)."""
    user = await get_user_from_request(request)
    if not user or not await check_is_admin(user["id"], user["username"]):
        return web.json_response({"error": "Доступ запрещен (требуются права администратора)"}, status=403)

    content_type_hdr = request.headers.get("Content-Type", "")
    photo_bytes = None
    photo_filename = None

    if "multipart/form-data" in content_type_hdr:
        reader = await request.multipart()
        form_data = {}
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "photo" and part.filename:
                photo_filename = part.filename
                photo_bytes = await part.read()
            else:
                val = await part.text()
                form_data[part.name] = val
        data = form_data
    else:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Некорректный формат данных"}, status=400)

    try:
        category_id = int(data.get("category_id", 0))
        name = str(data.get("name", "")).strip()
        description = str(data.get("description", "")).strip()
        price_raw = float(str(data.get("price", "0")).replace(",", "."))
        price_cents = max(1, int(round(price_raw * 100)))
        kind = str(data.get("kind", "reusable")).strip().lower()
        if kind not in ("reusable", "oneoff"):
            kind = "reusable"
        content_value = str(data.get("content_value", "")).strip()
    except Exception as e:
        return web.json_response({"error": f"Ошибка входных данных: {e}"}, status=400)

    if not name:
        return web.json_response({"error": "Укажите название товара"}, status=400)
    if not category_id:
        return web.json_response({"error": "Выберите раздел для товара"}, status=400)

    # Создаем товар в БД
    if kind == "reusable":
        pid = await db.add_product(
            category_id=category_id,
            name=name,
            description=description,
            price=price_cents,
            kind="reusable",
            content_type="text",
            content_value=content_value
        )
    else:
        pid = await db.add_product(
            category_id=category_id,
            name=name,
            description=description,
            price=price_cents,
            kind="oneoff"
        )
        lines = [line.strip() for line in content_value.splitlines() if line.strip()]
        if lines:
            items_to_add = [("text", line) for line in lines]
            await db.add_items(pid, items_to_add)

    # Если загружено фото
    if photo_bytes and len(photo_bytes) > 0:
        photos_dir = BASE_DIR / "photos"
        photos_dir.mkdir(exist_ok=True)
        ext = os.path.splitext(photo_filename or "photo.jpg")[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"
        saved_name = f"product_{pid}_photo_{uuid.uuid4().hex[:8]}{ext}"
        saved_path = photos_dir / saved_name
        with open(saved_path, "wb") as f:
            f.write(photo_bytes)
        rel_photo_path = f"photos/{saved_name}"
        await db.add_product_photo(pid, rel_photo_path)

    # Обновляем catalog.json для витрины
    await export_catalog_json()

    return web.json_response({
        "status": "ok",
        "product_id": pid,
        "message": f"Товар «{name}» успешно добавлен!"
    })


async def handle_admin_product_delete(request: web.Request):
    """Удаление (скрытие) товара из каталога."""
    user = await get_user_from_request(request)
    if not user or not await check_is_admin(user["id"], user["username"]):
        return web.json_response({"error": "Доступ запрещен"}, status=403)

    data = await request.json()
    prod_id = int(data.get("product_id", 0))
    if not prod_id:
        return web.json_response({"error": "Укажите product_id"}, status=400)

    # Скрываем товар из витрины (visible = 0)
    await db.conn.execute("UPDATE products SET visible = 0 WHERE id = ?", (prod_id,))
    await db.conn.commit()

    await export_catalog_json()
    return web.json_response({"status": "ok", "message": "Товар удален из каталога"})


async def handle_admin_pricing_apply(request: web.Request):
    """Применение скидки или наценки (аналог handlers/admin.py)."""
    user = await get_user_from_request(request)
    if not user or not await check_is_admin(user["id"], user["username"]):
        return web.json_response({"error": "Доступ запрещен"}, status=403)

    data = await request.json()
    scope = data.get("scope", "all")  # all | cat | prod
    op = data.get("op", "discount")   # discount | markup
    target_id = data.get("target_id")
    try:
        percent = float(data.get("percent", 0))
        if percent <= 0 or (op == "discount" and percent >= 100):
            return web.json_response({"error": "Процент должен быть от 1 до 99"}, status=400)
    except Exception:
        return web.json_response({"error": "Неверное значение процента"}, status=400)

    pid = int(target_id) if (scope == "prod" and target_id) else None
    cid = int(target_id) if (scope == "cat" and target_id) else None

    if op == "discount":
        count, updated = await db.apply_discount(percent=percent, product_id=pid, category_id=cid)
        msg = f"Скидка -{percent:g}% успешно применена к {count} товарам!"
    else:
        count, updated = await db.apply_markup(percent=percent, product_id=pid, category_id=cid)
        msg = f"Цены успешно повышены на +{percent:g}% для {count} товаров!"

    await export_catalog_json()
    return web.json_response({
        "status": "ok",
        "count": count,
        "updated": updated,
        "message": msg
    })


async def handle_admin_pricing_reset(request: web.Request):
    """Сброс скидок обратно к базовой цене old_price (аналог handlers/admin.py)."""
    user = await get_user_from_request(request)
    if not user or not await check_is_admin(user["id"], user["username"]):
        return web.json_response({"error": "Доступ запрещен"}, status=403)

    data = await request.json()
    scope = data.get("scope", "all")
    target_id = data.get("target_id")

    pid = int(target_id) if (scope == "prod" and target_id) else None
    cid = int(target_id) if (scope == "cat" and target_id) else None

    count = await db.reset_discounts(product_id=pid, category_id=cid)
    await export_catalog_json()
    return web.json_response({
        "status": "ok",
        "count": count,
        "message": f"Скидки сброшены! Восстановлены базовые цены для {count} товаров."
    })


async def handle_admin_pricing_summary(request: web.Request):
    """Сводка цен и скидок для предпросмотра."""
    user = await get_user_from_request(request)
    if not user or not await check_is_admin(user["id"], user["username"]):
        return web.json_response({"error": "Доступ запрещен"}, status=403)

    pid_raw = request.query.get("product_id")
    cid_raw = request.query.get("category_id")
    pid = int(pid_raw) if pid_raw and pid_raw.isdigit() else None
    cid = int(cid_raw) if cid_raw and cid_raw.isdigit() else None

    stats = await db.get_pricing_summary(product_id=pid, category_id=cid)
    return web.json_response({"status": "ok", "summary": stats})


async def handle_index(request: web.Request):
    """Отдает главную страницу сайта."""
    root_index = BASE_DIR / "index.html"
    if root_index.exists():
        return web.FileResponse(root_index)
    index_file = BASE_DIR / "web" / "index.html"
    return web.FileResponse(index_file)


# ==========================================
# APPLICATION SETUP
# ==========================================

async def on_startup(app: web.Application):
    await db.connect()
    await db.conn.execute("""
        CREATE TABLE IF NOT EXISTS site_auth_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL
        )
    """)
    await db.conn.execute("""
        CREATE TABLE IF NOT EXISTS site_otp_codes (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            code TEXT,
            created_at REAL,
            attempts INTEGER DEFAULT 0
        )
    """)
    await db.conn.execute("""
        CREATE TABLE IF NOT EXISTS site_sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER,
            username TEXT,
            created_at REAL
        )
    """)
    await db.conn.execute("""
        CREATE TABLE IF NOT EXISTS site_tonkeeper_orders (
            topup_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            amount_usd REAL NOT NULL,
            amount_cents INTEGER NOT NULL,
            amount_ton REAL NOT NULL,
            nanotons INTEGER NOT NULL,
            comment TEXT NOT NULL,
            wallet TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL,
            paid_at REAL
        )
    """)
    await db.conn.commit()

    # Загружаем сохраненные сессии из БД в память
    try:
        cur = await db.conn.execute("SELECT token, user_id, username, created_at FROM site_sessions")
        loaded_cnt = 0
        for row in await cur.fetchall():
            SESSIONS[row[0]] = {"user_id": row[1], "username": row[2], "created_at": row[3]}
            loaded_cnt += 1
        logger.info(f"Восстановлено {loaded_cnt} активных сессий пользователей из БД.")
    except Exception as e:
        logger.warning(f"Ошибка загрузки сессий: {e}")

    try:
        get_payments()
    except Exception as e:
        logger.warning(f"Инициализация платежного шлюза отложена: {e}")
    logger.info("Подключение к shop.db успешно установлено.")

    # Фоновый запуск Telegram-бота при RUN_BOT=true (для облачных хостингов)
    asyncio.create_task(start_bot_process())


bot_process = None

async def start_bot_process():
    global bot_process
    run_bot = os.getenv("RUN_BOT", "false").lower() in ("true", "1", "yes")
    if not run_bot:
        return
    if not config.bot_token:
        logger.warning("RUN_BOT включен, но BOT_TOKEN не настроен в переменных окружения.")
        return
    try:
        logger.info("Запуск Telegram-бота (bot.py) в фоновом режиме...")
        bot_process = await asyncio.create_subprocess_exec(
            sys.executable, str(BASE_DIR / "bot.py")
        )
        logger.info(f"Telegram-бот успешно запущен (PID: {bot_process.pid})")
    except Exception as e:
        logger.error(f"Не удалось запустить bot.py: {e}")


async def on_cleanup(app: web.Application):
    global payments, bot_process
    if bot_process:
        try:
            bot_process.terminate()
            await bot_process.wait()
            logger.info("Фоновый процесс Telegram-бота остановлен.")
        except Exception:
            pass
    if payments:
        try:
            await payments.close()
        except Exception:
            pass
    await db.close()
    logger.info("Соединения базы данных и платежей закрыты.")


@web.middleware
async def cors_middleware(request: web.Request, handler):
    origin = request.headers.get("Origin") or "*"
    if request.method == "OPTIONS":
        response = web.Response(status=200, text="")
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex
        except Exception as e:
            logger.exception(f"Необработанная ошибка {request.method} {request.path}: {e}")
            response = web.json_response({"error": "Внутренняя ошибка сервера"}, status=500)

    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept, Origin"
    if origin != "*":
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response


def create_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # API маршруты
    app.router.add_get("/api/init", handle_init)
    app.router.add_get("/api/catalog", handle_catalog)
    app.router.add_get("/api/product/{id}", handle_product_detail)

    # Авторизация
    app.router.add_post("/api/auth/send_code", handle_auth_send_code)
    app.router.add_post("/api/auth/verify_code", handle_auth_verify_code)
    app.router.add_post("/api/auth/identifier", handle_auth_identifier)
    app.router.add_post("/api/auth/bot_create", handle_auth_bot_create)
    app.router.add_get("/api/auth/bot_poll/{token}", handle_auth_bot_poll)
    app.router.add_post("/api/auth/telegram", handle_auth_telegram)
    app.router.add_post("/api/auth/test_login", handle_auth_demo)
    app.router.add_post("/api/auth/logout", handle_auth_logout)
    app.router.add_get("/api/user/me", handle_user_me)

    # Админ-панель
    app.router.add_get("/api/admin/check", handle_admin_check)
    app.router.add_get("/api/admin/products", handle_admin_products)
    app.router.add_post("/api/admin/product/add", handle_admin_product_add)
    app.router.add_post("/api/admin/product/delete", handle_admin_product_delete)
    app.router.add_post("/api/admin/pricing/apply", handle_admin_pricing_apply)
    app.router.add_post("/api/admin/pricing/reset", handle_admin_pricing_reset)
    app.router.add_get("/api/admin/pricing/summary", handle_admin_pricing_summary)

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
    app.router.add_static("/web/", path=str(web_dir), name="web")
    app.router.add_get("/catalog.json", lambda r: web.FileResponse(BASE_DIR / "catalog.json"))

    # Главная страница
    app.router.add_get("/", handle_index)

    return app


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Запуск веб-сайта магазина на http://localhost:{port}")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)
