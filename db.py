import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER NOT NULL DEFAULT 0,
    referrer_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    video_file_id TEXT,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('oneoff', 'reusable')),
    content_type TEXT,
    content_value TEXT,
    visible INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS product_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    content_type TEXT NOT NULL,
    content_value TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'free' CHECK (status IN ('free', 'reserved', 'sold')),
    reserved_until TEXT,
    purchase_id INTEGER
);

CREATE TABLE IF NOT EXISTS product_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    file_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER,
    product_name TEXT NOT NULL,
    price INTEGER NOT NULL,
    method TEXT NOT NULL,
    content_type TEXT,
    content_value TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    product_id INTEGER,
    item_id INTEGER,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    pay_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS referral_earnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL,
    referral_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    percent INTEGER NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT,
    product_id INTEGER,
    product_name TEXT,
    rating INTEGER,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mailings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_text TEXT NOT NULL,
    created_by_admin TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    sent_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    mirror_id INTEGER DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS mailing_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mailing_id INTEGER NOT NULL REFERENCES mailings(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mirrors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_token TEXT UNIQUE NOT NULL,
    bot_username TEXT,
    owner_id INTEGER NOT NULL,
    markup_percent INTEGER NOT NULL DEFAULT 0,
    greeting_text TEXT,
    banner_file_id TEXT,
    theme_color TEXT DEFAULT 'dark',
    channel_username TEXT,
    channel_link TEXT,
    balance INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mirror_users (
    user_id INTEGER NOT NULL,
    mirror_id INTEGER NOT NULL REFERENCES mirrors(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, mirror_id)
);

CREATE TABLE IF NOT EXISTS withdrawal_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mirror_id INTEGER NOT NULL REFERENCES mirrors(id) ON DELETE CASCADE,
    owner_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    requisites TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'rejected')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    creator_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'claimed')),
    claimed_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    claimed_at TEXT
);

CREATE TABLE IF NOT EXISTS promocodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    reward_type TEXT NOT NULL CHECK (reward_type IN ('bonus', 'discount')),
    value INTEGER NOT NULL,
    max_uses INTEGER NOT NULL DEFAULT 1,
    max_uses_per_user INTEGER NOT NULL DEFAULT 1,
    used_count INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS promocode_activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    promo_id INTEGER NOT NULL REFERENCES promocodes(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(promo_id, user_id)
);

CREATE TABLE IF NOT EXISTS containers_summary (
    user_id INTEGER PRIMARY KEY,
    total_received INTEGER NOT NULL DEFAULT 0,
    opened INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS container_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event TEXT NOT NULL,
    amount_rub INTEGER DEFAULT 0,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()
        # Миграция: добавляем колонку currency, если её нет (не ломаем существующую БД)
        try:
            await self.conn.execute("ALTER TABLE users ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD'")
            await self.conn.commit()
        except Exception:
            # Если колонка уже есть или другой ошибка - игнорируем
            pass

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    # --- пользователи ---

    async def get_user(self, user_id: int):
        cur = await self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return await cur.fetchone()

    async def get_or_create_user(self, user_id: int, username: str | None, referrer_id: int | None = None):
        row = await self.get_user(user_id)
        if row:
            needs_commit = False
            # Обновляем username если изменился
            if username and row["username"] != username:
                await self.conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
                needs_commit = True
            # ← ГЛАВНЫЙ ФИКС: если реферера нет, но он передан — сохраняем
            # (middleware создаёт юзера без реферера, cmd_start передаёт его позже)
            if referrer_id and not row["referrer_id"] and referrer_id != user_id:
                ref_exists = await self.get_user(referrer_id)
                if ref_exists:
                    await self.conn.execute(
                        "UPDATE users SET referrer_id = ? WHERE id = ?", (referrer_id, user_id)
                    )
                    needs_commit = True
            if needs_commit:
                await self.conn.commit()
            return await self.get_user(user_id)
        if referrer_id == user_id or (referrer_id is not None and await self.get_user(referrer_id) is None):
            referrer_id = None
        # INSERT OR IGNORE — защита от параллельных запросов одного пользователя
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (id, username, referrer_id, currency) VALUES (?, ?, ?, ?)",
            (user_id, username, referrer_id, 'USD'),
        )
        await self.conn.commit()
        return await self.get_user(user_id)

    async def set_user_currency(self, user_id: int, currency: str) -> None:
        if currency not in ('USD', 'RUB'):
            raise ValueError('unsupported currency')
        await self.conn.execute("UPDATE users SET currency = ? WHERE id = ?", (currency, user_id))
        await self.conn.commit()

    async def add_balance(self, user_id: int, amount: int) -> None:
        await self.conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
        await self.conn.commit()

    async def get_user_stats(self, user_id: int) -> dict:
        """Возвращает количество заказов, выполненных заказов и сумму потраченного (в центах)."""
        cur = await self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(price), 0) FROM purchases WHERE user_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        count = row[0] if row else 0
        spent_cents = row[1] if row else 0
        return {
            "total_orders": count,
            "completed_orders": count,
            "total_spent_cents": spent_cents
        }

    # --- настройки ---

    async def get_setting(self, key: str) -> str | None:
        cur = await self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.conn.commit()

    async def delete_setting(self, key: str) -> None:
        await self.conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        await self.conn.commit()

    # --- разделы ---

    async def add_category(self, name: str) -> int:
        cur = await self.conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        await self.conn.commit()
        return cur.lastrowid

    async def list_categories(self):
        cur = await self.conn.execute("SELECT * FROM categories ORDER BY position, id")
        return await cur.fetchall()

    async def get_category(self, category_id: int):
        cur = await self.conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
        return await cur.fetchone()

    async def rename_category(self, category_id: int, name: str) -> None:
        await self.conn.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
        await self.conn.commit()

    async def set_category_video(self, category_id: int, media: str | None) -> None:
        await self.conn.execute("UPDATE categories SET video_file_id = ? WHERE id = ?", (media, category_id))
        await self.conn.commit()

    async def delete_category(self, category_id: int) -> None:
        await self.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        await self.conn.commit()

    async def count_products(self, category_id: int) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) FROM products WHERE category_id = ?", (category_id,))
        return (await cur.fetchone())[0]

    # --- товары ---

    async def add_product(self, category_id: int, name: str, description: str, price: int,
                          kind: str, content_type: str | None = None, content_value: str | None = None) -> int:
        cur = await self.conn.execute(
            "INSERT INTO products (category_id, name, description, price, kind, content_type, content_value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (category_id, name, description, price, kind, content_type, content_value),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_product(self, product_id: int):
        cur = await self.conn.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        return await cur.fetchone()

    async def list_products(self, category_id: int, visible_only: bool = True):
        sql = "SELECT * FROM products WHERE category_id = ?"
        if visible_only:
            sql += " AND visible = 1"
        cur = await self.conn.execute(sql + " ORDER BY id", (category_id,))
        return await cur.fetchall()

    async def search_products(self, query: str):
        q = query.lower()
        cur = await self.conn.execute("SELECT * FROM products WHERE visible = 1 ORDER BY id")
        rows = await cur.fetchall()
        return [p for p in rows if q in p["name"].lower() or q in (p["description"] or "").lower()]

    async def set_product_field(self, product_id: int, field: str, value) -> None:
        if field not in ("name", "description", "price"):
            raise ValueError(f"недопустимое поле: {field}")
        await self.conn.execute(f"UPDATE products SET {field} = ? WHERE id = ?", (value, product_id))
        await self.conn.commit()

    async def set_product_content(self, product_id: int, content_type: str, content_value: str) -> None:
        await self.conn.execute(
            "UPDATE products SET content_type = ?, content_value = ? WHERE id = ?",
            (content_type, content_value, product_id),
        )
        await self.conn.commit()

    async def toggle_visible(self, product_id: int) -> None:
        await self.conn.execute("UPDATE products SET visible = 1 - visible WHERE id = ?", (product_id,))
        await self.conn.commit()

    async def delete_product(self, product_id: int) -> None:
        await self.conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await self.conn.commit()

    # --- фото товаров ---

    async def list_product_photos(self, product_id: int) -> list:
        cur = await self.conn.execute(
            "SELECT * FROM product_photos WHERE product_id = ? ORDER BY position, id",
            (product_id,),
        )
        return await cur.fetchall()

    async def count_product_photos(self, product_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM product_photos WHERE product_id = ?", (product_id,))
        return (await cur.fetchone())[0]

    async def add_product_photo(self, product_id: int, file_id: str) -> int:
        cur = await self.conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM product_photos WHERE product_id = ?",
            (product_id,),
        )
        position = (await cur.fetchone())[0]
        cur = await self.conn.execute(
            "INSERT INTO product_photos (product_id, file_id, position) VALUES (?, ?, ?)",
            (product_id, file_id, position),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def delete_product_photo(self, photo_id: int) -> None:
        await self.conn.execute("DELETE FROM product_photos WHERE id = ?", (photo_id,))
        await self.conn.commit()

    async def clear_product_photos(self, product_id: int) -> None:
        await self.conn.execute("DELETE FROM product_photos WHERE product_id = ?", (product_id,))
        await self.conn.commit()

    # --- единицы одноразовых товаров ---

    async def stock(self, product_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM product_items WHERE product_id = ? AND status = 'free'", (product_id,))
        return (await cur.fetchone())[0]

    async def add_items(self, product_id: int, items: list[tuple[str, str]]) -> None:
        await self.conn.executemany(
            "INSERT INTO product_items (product_id, content_type, content_value) VALUES (?, ?, ?)",
            [(product_id, t, v) for t, v in items],
        )
        await self.conn.commit()

    async def reserve_item(self, product_id: int, minutes: int = 30) -> int | None:
        cur = await self.conn.execute(
            "UPDATE product_items SET status = 'reserved', reserved_until = datetime('now', ?) "
            "WHERE id = (SELECT id FROM product_items WHERE product_id = ? AND status = 'free' LIMIT 1) "
            "RETURNING id",
            (f"{minutes} minutes", product_id),
        )
        row = await cur.fetchone()
        await self.conn.commit()
        return row["id"] if row else None

    async def release_item(self, item_id: int) -> None:
        await self.conn.execute(
            "UPDATE product_items SET status = 'free', reserved_until = NULL "
            "WHERE id = ? AND status = 'reserved'", (item_id,))
        await self.conn.commit()

    async def release_expired(self) -> None:
        await self.conn.execute(
            "UPDATE product_items SET status = 'free', reserved_until = NULL "
            "WHERE status = 'reserved' AND reserved_until < datetime('now')")
        await self.conn.commit()

    # --- покупки ---

    async def buy_with_balance(self, user_id: int, product_id: int) -> dict:
        conn = self.conn
        await conn.execute("BEGIN IMMEDIATE")
        try:
            cur = await conn.execute("SELECT * FROM products WHERE id = ? AND visible = 1", (product_id,))
            p = await cur.fetchone()
            if not p:
                await conn.execute("ROLLBACK")
                return {"status": "gone"}
            cur = await conn.execute(
                "UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?",
                (p["price"], user_id, p["price"]),
            )
            if cur.rowcount == 0:
                await conn.execute("ROLLBACK")
                return {"status": "no_funds"}
            item = None
            if p["kind"] == "oneoff":
                cur = await conn.execute(
                    "SELECT * FROM product_items WHERE product_id = ? AND status = 'free' LIMIT 1",
                    (product_id,),
                )
                item = await cur.fetchone()
                if not item:
                    await conn.execute("ROLLBACK")
                    return {"status": "out_of_stock"}
                content_type, content_value = item["content_type"], item["content_value"]
            else:
                content_type, content_value = p["content_type"], p["content_value"]
            cur = await conn.execute(
                "INSERT INTO purchases (user_id, product_id, product_name, price, method, content_type, content_value) "
                "VALUES (?, ?, ?, ?, 'balance', ?, ?)",
                (user_id, product_id, p["name"], p["price"], content_type, content_value),
            )
            purchase_id = cur.lastrowid
            if item is not None:
                await conn.execute(
                    "UPDATE product_items SET status = 'sold', purchase_id = ?, reserved_until = NULL WHERE id = ?",
                    (purchase_id, item["id"]),
                )
            await conn.commit()
            return {"status": "ok", "purchase_id": purchase_id, "name": p["name"], "price": p["price"],
                    "content_type": content_type, "content_value": content_value}
        except Exception:
            await conn.execute("ROLLBACK")
            raise

    async def list_purchases(self, user_id: int, limit: int = 10):
        cur = await self.conn.execute(
            "SELECT * FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
        return await cur.fetchall()

    async def count_purchases(self, user_id: int) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) FROM purchases WHERE user_id = ?", (user_id,))
        return (await cur.fetchone())[0]

    async def get_purchase(self, purchase_id: int):
        cur = await self.conn.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
        return await cur.fetchone()

    # --- счета ---

    async def create_invoice(self, invoice_id: int, user_id: int, purpose: str, amount: int,
                             pay_url: str, product_id: int | None = None, item_id: int | None = None) -> None:
        await self.conn.execute(
            "INSERT INTO invoices (invoice_id, user_id, purpose, product_id, item_id, amount, pay_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (invoice_id, user_id, purpose, product_id, item_id, amount, pay_url),
        )
        await self.conn.commit()

    async def get_invoice(self, invoice_id: int):
        cur = await self.conn.execute("SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,))
        return await cur.fetchone()

    async def mark_invoice_paid(self, invoice_id: int) -> bool:
        cur = await self.conn.execute(
            "UPDATE invoices SET status = 'paid' WHERE invoice_id = ? AND status = 'active'", (invoice_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    async def mark_invoice_expired(self, invoice_id: int) -> None:
        await self.conn.execute(
            "UPDATE invoices SET status = 'expired' WHERE invoice_id = ? AND status = 'active'", (invoice_id,))
        await self.conn.commit()

    async def list_active_invoices(self):
        cur = await self.conn.execute("SELECT * FROM invoices WHERE status = 'active'")
        return await cur.fetchall()

    # --- рефералка ---

    async def count_invited(self, user_id: int) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        return (await cur.fetchone())[0]

    async def count_referral_clients(self, referrer_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(DISTINCT i.user_id) FROM invoices i "
            "JOIN users u ON u.id = i.user_id "
            "WHERE u.referrer_id = ? AND i.status = 'paid'",
            (referrer_id,),
        )
        return (await cur.fetchone())[0]

    async def total_referral_earned(self, user_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM referral_earnings WHERE referrer_id = ?", (user_id,))
        return (await cur.fetchone())[0]

    async def add_referral_earning(self, referrer_id: int, referral_id: int,
                                   amount: int, percent: int, source: str) -> None:
        conn = self.conn
        await conn.execute("BEGIN IMMEDIATE")
        try:
            await conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, referrer_id))
            await conn.execute(
                "INSERT INTO referral_earnings (referrer_id, referral_id, amount, percent, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (referrer_id, referral_id, amount, percent, source),
            )
            await conn.commit()
        except Exception:
            await conn.execute("ROLLBACK")
            raise

    # --- статистика ---

    async def stats(self) -> dict:
        async def one(sql: str):
            cur = await self.conn.execute(sql)
            return (await cur.fetchone())[0]

        users = await one("SELECT COUNT(*) FROM users")
        sales = await one("SELECT COUNT(*) FROM purchases")
        revenue = await one("SELECT COALESCE(SUM(price), 0) FROM purchases")
        cur = await self.conn.execute(
            "SELECT product_name, COUNT(*) AS c FROM purchases "
            "GROUP BY product_name ORDER BY c DESC LIMIT 5")
        top = await cur.fetchall()
        return {"users": users, "sales": sales, "revenue": revenue, "top": top}

    # --- логи ---

    async def add_log(self, user_id: int, username: str | None, action: str, details: str | None = None) -> None:
       await self.conn.execute(
           "INSERT INTO logs (user_id, username, action, details) VALUES (?, ?, ?, ?)",
           (user_id, username, action, details),
       )
       await self.conn.commit()

    async def get_user_logs(self, user_id: int, limit: int = 10):
       cur = await self.conn.execute(
           "SELECT * FROM logs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
           (user_id, limit),
       )
       return await cur.fetchall()

    async def list_all_logs(self, limit: int = 50):
       cur = await self.conn.execute(
           "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?",
           (limit,),
       )
       return await cur.fetchall()

    # --- отзывы ---

    async def add_review(self, user_id: int, username: str | None, product_id: int | None, 
                       product_name: str | None, text: str, rating: int | None = None) -> None:
       await self.conn.execute(
           "INSERT INTO reviews (user_id, username, product_id, product_name, text, rating) "
           "VALUES (?, ?, ?, ?, ?, ?)",
           (user_id, username, product_id, product_name, text, rating),
       )
       await self.conn.commit()

    async def list_reviews(self, limit: int = 20):
       cur = await self.conn.execute(
           "SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?",
           (limit,),
       )
       return await cur.fetchall()

    # --- рассылка ---

    async def create_mailing(self, message_text: str, created_by_admin: str, user_ids: list[int] | None = None) -> int:
       cur = await self.conn.execute(
           "INSERT INTO mailings (message_text, created_by_admin) VALUES (?, ?)",
           (message_text, created_by_admin),
       )
       mailing_id = cur.lastrowid
        
       if user_ids:
           await self.conn.executemany(
               "INSERT INTO mailing_queue (mailing_id, user_id) VALUES (?, ?)",
               [(mailing_id, uid) for uid in user_ids],
           )
           await self.conn.execute(
               "UPDATE mailings SET total_count = ? WHERE id = ?",
               (len(user_ids), mailing_id),
           )
       await self.conn.commit()
       return mailing_id

    async def get_mailing_queue(self, status: str = "pending", limit: int = 10):
       cur = await self.conn.execute(
           "SELECT * FROM mailing_queue WHERE status = ? ORDER BY id LIMIT ?",
           (status, limit),
       )
       return await cur.fetchall()

    async def mark_mailing_sent(self, mailing_queue_id: int) -> None:
       cur = await self.conn.execute(
           "UPDATE mailing_queue SET status = 'sent' WHERE id = ?", (mailing_queue_id,)
       )
       await self.conn.execute(
           "UPDATE mailings SET sent_count = sent_count + 1 WHERE id IN "
           "(SELECT mailing_id FROM mailing_queue WHERE id = ?)",
           (mailing_queue_id,)
       )
       await self.conn.commit()

    async def list_all_users(self):
       cur = await self.conn.execute(
           "SELECT id, username, balance, created_at FROM users ORDER BY id"
       )
       return await cur.fetchall()

    async def search_users(self, query: str):
       """Поиск пользователя по ID или username"""
       try:
           user_id = int(query)
           cur = await self.conn.execute(
               "SELECT id, username, balance, created_at FROM users WHERE id = ?",
               (user_id,),
           )
           return await cur.fetchone()
       except ValueError:
           pass
        
       username = query.lstrip("@").lower()
       cur = await self.conn.execute(
           "SELECT id, username, balance, created_at FROM users WHERE LOWER(username) LIKE ?",
           (f"%{username}%",),
       )
       return await cur.fetchall()

    # --- выдача по прямому счёту ---

    async def fulfill_direct_purchase(self, inv) -> dict:
        conn = self.conn
        user_id, product_id, amount = inv["user_id"], inv["product_id"], inv["amount"]
        await conn.execute("BEGIN IMMEDIATE")
        try:
            cur = await conn.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            p = await cur.fetchone()
            item = None
            if p and p["kind"] == "oneoff":
                if inv["item_id"]:
                    cur = await conn.execute(
                        "SELECT * FROM product_items WHERE id = ? AND status IN ('reserved', 'free')",
                        (inv["item_id"],),
                    )
                    item = await cur.fetchone()
                if item is None:
                    cur = await conn.execute(
                        "SELECT * FROM product_items WHERE product_id = ? AND status = 'free' LIMIT 1",
                        (product_id,),
                    )
                    item = await cur.fetchone()
                if item is None:
                    await conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
                    await conn.commit()
                    return {"status": "refunded"}
                content_type, content_value = item["content_type"], item["content_value"]
            elif p:
                content_type, content_value = p["content_type"], p["content_value"]
            else:
                await conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
                await conn.commit()
                return {"status": "refunded"}
            cur = await conn.execute(
                "INSERT INTO purchases (user_id, product_id, product_name, price, method, content_type, content_value) "
                "VALUES (?, ?, ?, ?, 'direct', ?, ?)",
                (user_id, product_id, p["name"], amount, content_type, content_value),
            )
            purchase_id = cur.lastrowid
            if item is not None:
                await conn.execute(
                    "UPDATE product_items SET status = 'sold', purchase_id = ?, reserved_until = NULL WHERE id = ?",
                    (purchase_id, item["id"]),
                )
            await conn.commit()
            return {"status": "ok", "purchase_id": purchase_id, "name": p["name"], "price": amount,
                    "content_type": content_type, "content_value": content_value}
        except Exception:
            await conn.execute("ROLLBACK")
            raise

    # --- Зеркала (Mirrors) ---

    async def create_mirror(self, bot_token: str, bot_username: str, owner_id: int, markup_percent: int = 0) -> int:
        cur = await self.conn.execute(
            "INSERT INTO mirrors (bot_token, bot_username, owner_id, markup_percent) VALUES (?, ?, ?, ?)",
            (bot_token, bot_username, owner_id, markup_percent),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_mirror_by_id(self, mirror_id: int):
        cur = await self.conn.execute("SELECT * FROM mirrors WHERE id = ?", (mirror_id,))
        return await cur.fetchone()

    async def get_mirror_by_token(self, bot_token: str):
        cur = await self.conn.execute("SELECT * FROM mirrors WHERE bot_token = ?", (bot_token,))
        return await cur.fetchone()

    async def get_mirrors_by_owner(self, owner_id: int):
        cur = await self.conn.execute("SELECT * FROM mirrors WHERE owner_id = ?", (owner_id,))
        return await cur.fetchall()

    async def list_active_mirrors(self):
        cur = await self.conn.execute("SELECT * FROM mirrors WHERE is_active = 1")
        return await cur.fetchall()

    async def update_mirror_settings(self, mirror_id: int, **kwargs):
        allowed_fields = {"markup_percent", "greeting_text", "banner_file_id", "theme_color", "is_active", "channel_link", "channel_username"}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                params.append(val)
        if not updates:
            return
        params.append(mirror_id)
        sql = f"UPDATE mirrors SET {', '.join(updates)} WHERE id = ?"
        await self.conn.execute(sql, tuple(params))
        await self.conn.commit()

    async def register_mirror_user(self, user_id: int, mirror_id: int):
        await self.conn.execute(
            "INSERT OR IGNORE INTO mirror_users (user_id, mirror_id) VALUES (?, ?)",
            (user_id, mirror_id),
        )
        await self.conn.commit()

    async def get_mirror_users_count(self, mirror_id: int) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) as cnt FROM mirror_users WHERE mirror_id = ?", (mirror_id,))
        row = await cur.fetchone()
        return row["cnt"] if row else 0

    async def get_mirror_users(self, mirror_id: int) -> list:
        cur = await self.conn.execute("SELECT user_id FROM mirror_users WHERE mirror_id = ?", (mirror_id,))
        rows = await cur.fetchall()
        return [row["user_id"] for row in rows]

    async def add_mirror_balance(self, mirror_id: int, amount: int):
        await self.conn.execute("UPDATE mirrors SET balance = balance + ? WHERE id = ?", (amount, mirror_id))
        await self.conn.commit()

    # --- Выплаты Зеркал ---

    async def create_withdrawal_request(self, mirror_id: int, owner_id: int, amount: int, requisites: str) -> int:
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            cur = await self.conn.execute("SELECT balance FROM mirrors WHERE id = ?", (mirror_id,))
            row = await cur.fetchone()
            if not row or row["balance"] < amount:
                await self.conn.execute("ROLLBACK")
                raise ValueError("Недостаточно средств на балансе зеркала")
            await self.conn.execute("UPDATE mirrors SET balance = balance - ? WHERE id = ?", (amount, mirror_id))
            cur = await self.conn.execute(
                "INSERT INTO withdrawal_requests (mirror_id, owner_id, amount, requisites) VALUES (?, ?, ?, ?)",
                (mirror_id, owner_id, amount, requisites),
            )
            req_id = cur.lastrowid
            await self.conn.commit()
            return req_id
        except Exception:
            await self.conn.execute("ROLLBACK")
            raise

    async def list_pending_withdrawals(self):
        cur = await self.conn.execute("SELECT * FROM withdrawal_requests WHERE status = 'pending' ORDER BY id DESC")
        return await cur.fetchall()

    async def process_withdrawal(self, request_id: int, status: str):
        cur = await self.conn.execute("SELECT * FROM withdrawal_requests WHERE id = ?", (request_id,))
        req = await cur.fetchone()
        if not req or req["status"] != "pending":
            return False
        if status == "rejected":
            await self.conn.execute("UPDATE mirrors SET balance = balance + ? WHERE id = ?", (req["amount"], req["mirror_id"]))
        await self.conn.execute("UPDATE withdrawal_requests SET status = ? WHERE id = ?", (status, request_id))
        await self.conn.commit()
        return True

    # --- Чеки (Checks) ---

    async def create_check(self, creator_id: int, amount: int, code: str) -> bool:
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            cur = await self.conn.execute("SELECT balance FROM users WHERE id = ?", (creator_id,))
            user = await cur.fetchone()
            if not user or user["balance"] < amount:
                await self.conn.execute("ROLLBACK")
                return False
            await self.conn.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, creator_id))
            await self.conn.execute(
                "INSERT INTO checks (code, creator_id, amount) VALUES (?, ?, ?)",
                (code, creator_id, amount),
            )
            await self.conn.commit()
            return True
        except Exception:
            await self.conn.execute("ROLLBACK")
            raise

    async def claim_check(self, user_id: int, code: str) -> dict:
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            cur = await self.conn.execute("SELECT * FROM checks WHERE code = ?", (code,))
            chk = await cur.fetchone()
            if not chk:
                await self.conn.execute("ROLLBACK")
                return {"status": "not_found"}
            if chk["status"] != "active":
                await self.conn.execute("ROLLBACK")
                return {"status": "already_claimed"}
            
            await self.conn.execute(
                "UPDATE checks SET status = 'claimed', claimed_by = ?, claimed_at = datetime('now') WHERE id = ?",
                (user_id, chk["id"]),
            )
            await self.conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (chk["amount"], user_id))
            await self.conn.commit()
            return {"status": "ok", "amount": chk["amount"], "creator_id": chk["creator_id"]}
        except Exception:
            await self.conn.execute("ROLLBACK")
            raise

    # --- Промокоды (Promocodes) ---

    async def create_promocode(self, code: str, reward_type: str, value: int,
                               max_uses: int = 1, max_uses_per_user: int = 1) -> bool:
        try:
            await self.conn.execute(
                "INSERT INTO promocodes (code, reward_type, value, max_uses, max_uses_per_user) VALUES (?, ?, ?, ?, ?)",
                (code.upper(), reward_type, value, max_uses, max_uses_per_user),
            )
            await self.conn.commit()
            return True
        except Exception:
            return False

    async def activate_promocode(self, user_id: int, code: str) -> dict:
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            code_clean = code.strip().upper()
            cur = await self.conn.execute("SELECT * FROM promocodes WHERE code = ? AND is_active = 1", (code_clean,))
            promo = await cur.fetchone()
            if not promo:
                await self.conn.execute("ROLLBACK")
                return {"status": "not_found"}
            if promo["used_count"] >= promo["max_uses"]:
                await self.conn.execute("ROLLBACK")
                return {"status": "limit_reached"}

            # Проверяем сколько раз этот пользователь уже активировал промо
            cur = await self.conn.execute(
                "SELECT COUNT(*) FROM promocode_activations WHERE promo_id = ? AND user_id = ?",
                (promo["id"], user_id)
            )
            user_activations = (await cur.fetchone())[0]
            max_per_user = promo["max_uses_per_user"] if "max_uses_per_user" in promo.keys() else 1

            if user_activations >= max_per_user:
                await self.conn.execute("ROLLBACK")
                return {"status": "already_used"}

            await self.conn.execute(
                "INSERT INTO promocode_activations (promo_id, user_id) VALUES (?, ?)",
                (promo["id"], user_id),
            )
            await self.conn.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE id = ?", (promo["id"],))

            if promo["reward_type"] == "bonus":
                await self.conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (promo["value"], user_id))

            await self.conn.commit()

            # Получаем данные пользователя для уведомления
            cur = await self.conn.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            user_row = await cur.fetchone()
            username = user_row["username"] if user_row and user_row["username"] else None

            return {
                "status": "ok",
                "reward_type": promo["reward_type"],
                "value": promo["value"],
                "code": code_clean,
                "user_id": user_id,
                "username": username,
            }
        except Exception:
            await self.conn.execute("ROLLBACK")
            raise

    # --- Контейнеры (Containers) ---

    async def sync_user_containers(self, user_id: int, threshold_rub: int = 1000) -> int:
        """Sync containers based on total spent. Returns number of new containers credited."""
        # total price stored in cents USD
        cur = await self.conn.execute("SELECT COALESCE(SUM(price), 0) as s FROM purchases WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        total_price_cents = row["s"] if row else 0
        # convert to ruble cents: total_price_cents * EXCHANGE_RATE
        try:
            from texts import EXCHANGE_RATE
        except Exception:
            EXCHANGE_RATE = 90.0
        total_rub_cents = int(round(total_price_cents * EXCHANGE_RATE))
        threshold_cents = threshold_rub * 100
        should = total_rub_cents // threshold_cents
        cur = await self.conn.execute("SELECT total_received FROM containers_summary WHERE user_id = ?", (user_id,))
        r = await cur.fetchone()
        existing = r["total_received"] if r else 0
        diff = int(should - existing)
        if diff > 0:
            if r:
                await self.conn.execute("UPDATE containers_summary SET total_received = total_received + ? WHERE user_id = ?", (diff, user_id))
            else:
                await self.conn.execute("INSERT INTO containers_summary (user_id, total_received, opened) VALUES (?, ?, 0)", (user_id, diff))
            await self.conn.commit()
        return diff

    async def get_container_info(self, user_id: int, threshold_rub: int = 1000) -> dict:
        cur = await self.conn.execute("SELECT total_received, opened FROM containers_summary WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        total_received = row["total_received"] if row else 0
        opened = row["opened"] if row else 0
        available = total_received - opened
        try:
            from texts import EXCHANGE_RATE
        except Exception:
            EXCHANGE_RATE = 90.0
        cur = await self.conn.execute("SELECT COALESCE(SUM(price), 0) as s FROM purchases WHERE user_id = ?", (user_id,))
        srow = await cur.fetchone()
        total_price_cents = srow["s"] if srow else 0
        total_rub_cents = int(round(total_price_cents * EXCHANGE_RATE))
        threshold_cents = threshold_rub * 100
        rem = total_rub_cents % threshold_cents
        to_next = 0 if rem == 0 else (threshold_cents - rem) / 100.0
        return {"available": int(available), "total_received": int(total_received), "opened": int(opened), "to_next_rub": to_next}

    async def open_container(self, user_id: int, reward_rub: int) -> dict:
        cur = await self.conn.execute("SELECT total_received, opened FROM containers_summary WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        total_received = row["total_received"] if row else 0
        opened = row["opened"] if row else 0
        available = total_received - opened
        if available <= 0:
            return {"status": "no_available"}
        # mark opened
        await self.conn.execute("UPDATE containers_summary SET opened = opened + 1 WHERE user_id = ?", (user_id,))
        # credit user's balance (reward_rub converted to USD cents)
        try:
            from texts import EXCHANGE_RATE
        except Exception:
            EXCHANGE_RATE = 90.0
        usd_cents = int(round(reward_rub / EXCHANGE_RATE * 100))
        await self.conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (usd_cents, user_id))
        await self.conn.execute("INSERT INTO container_history (user_id, event, amount_rub, details) VALUES (?, ?, ?, ?)", (user_id, "opened", reward_rub, f"Получено {reward_rub}₽"))
        await self.conn.commit()
        return {"status": "ok", "reward_rub": reward_rub, "usd_cents": usd_cents}

    async def list_container_history(self, user_id: int, limit: int = 20):
        cur = await self.conn.execute("SELECT * FROM container_history WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
        return await cur.fetchall()

