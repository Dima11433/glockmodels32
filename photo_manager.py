import os
import aiofiles
from pathlib import Path
from aiogram import Bot

PHOTOS_DIR = Path(__file__).parent / "photos"
PHOTOS_DIR.mkdir(exist_ok=True)


async def download_and_save_photo(bot: Bot, file_id: str, product_id: int, photo_num: int) -> str:
    """Скачивает фото из Telegram и сохраняет локально.
    Возвращает относительный путь к сохранённому файлу в формате "photos/<name>".

    Раньше имена файлов генерировались как product_<product_id>_photo_<photo_num>.jpg —
    при загрузке баннеров для разных кнопок использовался product_id=0 и photo_num=0,
    из-за чего файлы перезаписывались. Теперь генерируется уникальное имя через uuid4,
    сохраняется оригинальное расширение файла (если доступно).
    """
    import uuid
    try:
        # Получаем информацию о файле
        file_info = await bot.get_file(file_id)

        # Скачиваем файл (возвращается объект с getvalue())
        file_bytes = await bot.download_file(file_info.file_path)
        data = file_bytes.getvalue()

        # Попытка определить расширение из пути файла
        suffix = Path(file_info.file_path).suffix or '.jpg'
        # Создаём уникальное имя
        filename = f"banner_{uuid.uuid4().hex}{suffix}"
        local_path = PHOTOS_DIR / filename

        # Сохраняем файл
        async with aiofiles.open(local_path, 'wb') as f:
            await f.write(data)

        # Возвращаем относительный путь
        return f"photos/{filename}"
    except Exception as e:
        print(f"Error downloading photo: {e}")
        # Если скачивание не удалось, возвращаем file_id как fallback
        return f"file_id:{file_id}"


def get_photo_path(photo_path: str) -> str:
    """Возвращает полный путь к файлу фото.
    Если это file_id, возвращает его как есть.
    """
    if photo_path.startswith("file_id:"):
        return photo_path[8:]  # Возвращаем file_id без префикса
    
    # Это локальный файл
    full_path = PHOTOS_DIR / photo_path.replace("photos/", "")
    if full_path.exists():
        return str(full_path)
    
    return None


async def migrate_photos(bot: Bot, db) -> int:
    """Мигрирует старые Telegram file_id в локальные файлы и обновляет product_photos.file_id и некоторые settings.
    Возвращает количество успешно мигрированных записей."""
    migrated = 0
    try:
        # --- product_photos ---
        cur = await db.conn.execute("SELECT * FROM product_photos ORDER BY product_id, position, id")
        rows = await cur.fetchall()
        for r in rows:
            old = r['file_id']
            pid = r['product_id']
            if not old:
                continue
            # Пропускаем уже локальные или явно URL/file_id-префиксы
            if old.startswith('photos/') or old.startswith('/photos/') or old.startswith('http') or old.startswith('file_id:'):
                continue
            try:
                saved = await download_and_save_photo(bot, old, pid, r.get('position', 0) if isinstance(r.get('position', 0), int) else 0)
                await db.conn.execute("UPDATE product_photos SET file_id = ? WHERE id = ?", (saved, r['id']))
                migrated += 1
            except Exception as e:
                print('migrate_photos error', e)
        await db.conn.commit()

        # --- settings (btn banners) ---
        cur = await db.conn.execute("SELECT key, value FROM settings WHERE key LIKE 'btn:banner%'")
        settings = await cur.fetchall()
        for s in settings:
            key = s['key']
            val = s['value']
            if not val:
                continue
            if val.startswith('photos/') or val.startswith('/photos/') or val.startswith('http') or val.startswith('file_id:'):
                continue
            try:
                saved = await download_and_save_photo(bot, val, 0, 0)
                await db.conn.execute("UPDATE settings SET value = ? WHERE key = ?", (saved, key))
                migrated += 1
            except Exception as e:
                print('migrate_settings_banner error', e)
        await db.conn.commit()

        # --- categories (video_file_id) ---
        cur = await db.conn.execute("SELECT id, video_file_id FROM categories WHERE video_file_id IS NOT NULL")
        cats = await cur.fetchall()
        for c in cats:
            vid = c['video_file_id']
            cid = c['id']
            if not vid:
                continue
            if vid.startswith('photos/') or vid.startswith('/photos/') or vid.startswith('http') or vid.startswith('file_id:'):
                continue
            try:
                saved = await download_and_save_photo(bot, vid, cid, 0)
                await db.conn.execute("UPDATE categories SET video_file_id = ? WHERE id = ?", (saved, cid))
                migrated += 1
            except Exception as e:
                print('migrate_category_video error', e)
        await db.conn.commit()

    except Exception as e:
        print('migrate_photos overall error', e)
    print(f"migrate_photos done: {migrated}")
    return migrated
