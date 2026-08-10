from aiogram.types import InputMediaPhoto, FSInputFile, InputFile, Message
from pathlib import Path

from db import Database

# Telegram media group limit
MAX_PHOTOS = 10

PHOTOS_DIR = Path(__file__).parent / "photos"


def media_of(message: Message) -> str | None:
    if message.video:
        return f"video|{message.video.file_id}"
    if message.animation:
        return f"anim|{message.animation.file_id}"
    return None


def photo_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    return None


async def send_media(message: Message, media: str, caption: str, markup=None) -> None:
    kind, file_id = media.split("|", 1)
    # Ограничиваем длину подписи
    if len(caption) > 1024:
        caption = caption[:1021] + "..."
    if kind == "anim":
        await message.answer_animation(file_id, caption=caption, reply_markup=markup)
    else:
        await message.answer_video(file_id, caption=caption, reply_markup=markup)


def is_valid_file_id(fid: str) -> bool:
    """Проверяем, что file_id - это валидная строка."""
    if not isinstance(fid, str):
        return False
    if not fid:
        return False
    # Telegram file_id должна быть минимум нескольких символов
    # Может содержать буквы, цифры, подчёркивание, дефис и т.д.
    # Главное - не пусто и не состоит из одного числа (ID товара)
    return len(fid) > 3


def get_photo_local_path(photo_path: str | None) -> Path | None:
    """Возвращает локальный путь к файлу фото, если он существует."""
    if not photo_path:
        return None
    
    # Если это путь, начинающийся с "photos/"
    if photo_path.startswith("photos/"):
        full_path = PHOTOS_DIR / photo_path.replace("photos/", "")
        if full_path.exists():
            return full_path
    
    # Если это полный путь
    full_path = Path(photo_path)
    if full_path.exists():
        return full_path
    
    return None


async def send_product_photos(message: Message, file_ids: list, caption: str, markup=None, parse_mode: str = "HTML") -> None:
    """Send product photos: album if several, single photo or plain text otherwise."""
    import logging
    logger = logging.getLogger(__name__)
    
    if not file_ids:
        await message.answer(caption, reply_markup=markup)
        return
    
    # Извлекаем file_id или path из Row объектов
    extracted_items = []  # Список tuple (file_id_or_path, is_file)
    
    for fid in file_ids[:MAX_PHOTOS]:
        file_id_or_path = None
        is_file = False
        
        if isinstance(fid, str):
            file_id_or_path = fid
        elif isinstance(fid, dict):
            file_id_or_path = fid.get('file_id')
        else:
            # Это Row объект из БД - достаём 'file_id' по названию колонки
            try:
                if hasattr(fid, 'keys') and 'file_id' in fid.keys():
                    file_id_or_path = fid['file_id']
            except (KeyError, TypeError, AttributeError):
                pass
        
        # Проверяем, это файл или file_id
        if file_id_or_path:
            file_id_or_path = str(file_id_or_path).strip()
            
            # Пытаемся найти локальный файл
            local_path = get_photo_local_path(file_id_or_path)
            if local_path:
                extracted_items.append((str(local_path), True))
                is_file = True
            elif is_valid_file_id(file_id_or_path):
                extracted_items.append((file_id_or_path, False))
    
    logger.info(f"send_product_photos: extracted {len(extracted_items)} photos from {len(file_ids)} input items")
    
    if not extracted_items:
        logger.warning(f"send_product_photos: no valid file_ids extracted, sending text only")
        await message.answer(caption, reply_markup=markup)
        return
    
    # Ограничиваем длину caption до 1024 символов для фото
    if len(caption) > 1024:
        caption = caption[:1021] + "..."
    
    if len(extracted_items) == 1:
        photo_path, is_file = extracted_items[0]
        try:
            logger.info(f"send_product_photos: sending single photo ({'file' if is_file else 'file_id'})")
            import os
            if is_file or (isinstance(photo_path, str) and os.path.exists(photo_path)):
                await message.answer_photo(FSInputFile(photo_path), caption=caption,
                                           reply_markup=markup, parse_mode=parse_mode)
            else:
                await message.answer_photo(photo_path, caption=caption,
                                           reply_markup=markup, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"send_product_photos: error sending single photo: {e}")
            await message.answer(caption, reply_markup=markup, parse_mode=parse_mode)
        return
    
    # Несколько фото - отправляем альбом
    media = []
    for i, (photo_path, is_file) in enumerate(extracted_items):
        try:
            # Если локальный файл — упаковываем в InputFile, иначе передаём file_id/URL
            if is_file or (isinstance(photo_path, str) and Path(photo_path).exists()):
                media.append(InputMediaPhoto(media=FSInputFile(photo_path), caption=caption if i == 0 else None))
            else:
                media.append(InputMediaPhoto(media=photo_path, caption=caption if i == 0 else None))
        except Exception as e:
            logger.error(f"send_product_photos: error preparing media {i}: {e}")
    
    if not media:
        await message.answer(caption, reply_markup=markup)
        return
    
    try:
        logger.info(f"send_product_photos: sending media group with {len(media)} photos")
        await message.answer_media_group(media)
        # Отправляем кнопки отдельно после альбома
        if markup is not None:
            await message.answer("Выберите действие:", reply_markup=markup)
    except Exception as e:
        logger.error(f"send_product_photos: error sending media group: {e}")
        # Fallback - пробуем отправить каждое фото отдельно
        try:
            logger.info(f"send_product_photos: fallback - sending photos individually")
            for i, (photo_path, is_file) in enumerate(extracted_items):
                photo_caption = caption if i == 0 else None
                try:
                    if is_file or (isinstance(photo_path, str) and Path(photo_path).exists()):
                        await message.answer_photo(InputFile(photo_path), caption=photo_caption)
                    else:
                        await message.answer_photo(photo_path, caption=photo_caption)
                except Exception as e:
                    logger.error(f"send_product_photos: error sending individual photo {i}: {e}")
            if markup is not None:
                await message.answer("Выберите действие:", reply_markup=markup)
        except Exception as e2:
            logger.error(f"send_product_photos: error in fallback: {e2}")
            # Последний fallback - отправляем только текст
            await message.answer(caption, reply_markup=markup)


async def send_tab(message: Message, db: Database, video_key: str, text: str, markup=None, banner_suffix: str | None = None) -> None:
    """Send a tab: prefer video (video_key). If no video, show banner for banner_suffix (btn:banner:<suffix>),
    then fallback to global btn:banner, then plaintext."""
    media = await db.get_setting(video_key)
    if media:
        try:
            await send_media(message, media, text, markup)
            return
        except Exception:
            pass

    # per-button banner
    if banner_suffix:
        banner_key = f"btn:banner:{banner_suffix}"
        banner = await db.get_setting(banner_key)
        if banner:
            try:
                caption = text[:1024] if len(text) > 1024 else text
                local = get_photo_local_path(banner)
                if local:
                    await message.answer_photo(FSInputFile(str(local)), caption=caption, reply_markup=markup)
                else:
                    fid = banner[8:] if banner.startswith("file_id:") else banner
                    await message.answer_photo(fid, caption=caption, reply_markup=markup)
                return
            except Exception:
                pass

    # global banner
    banner = await db.get_setting("btn:banner")
    if banner:
        try:
            caption = text[:1024] if len(text) > 1024 else text
            local = get_photo_local_path(banner)
            if local:
                await message.answer_photo(FSInputFile(str(local)), caption=caption, reply_markup=markup)
            else:
                fid = banner[8:] if banner.startswith("file_id:") else banner
                await message.answer_photo(fid, caption=caption, reply_markup=markup)
            return
        except Exception:
            pass

    await message.answer(text, reply_markup=markup)


async def send_menu(message: Message, db: Database, text: str, markup=None) -> None:
    """Send main menu: show per-button descriptions under the menu if provided in settings.

    For each button in keyboards.MAIN_BUTTONS we check settings key btn:desc:<suffix>.
    If present, append short descriptions under the main message.
    """
    # collect per-button descriptions
    desc_lines = []
    try:
        import keyboards
        import texts as _texts
        for suffix, title in keyboards.MAIN_BUTTONS:
            desc = await db.get_setting(f"btn:desc:{suffix}") or getattr(_texts, f"BTN_DESC_{suffix.upper()}", "")
            if desc:
                desc_lines.append(f"{title} — {desc}")
    except Exception:
        desc_lines = []

    caption = text
    if desc_lines:
        caption = f"{text}\n\n" + "\n".join(desc_lines)

    # Ограничиваем длину до 1024 символов для фото
    if len(caption) > 1024:
        caption = caption[:1021] + "..."

    # prefer global banner if any
    banner = await db.get_setting("btn:banner")
    if banner:
        try:
            caption = caption[:1024] if len(caption) > 1024 else caption
            local = get_photo_local_path(banner)
            if local:
                await message.answer_photo(FSInputFile(str(local)), caption=caption, reply_markup=markup)
                return
            fid = banner[8:] if banner.startswith("file_id:") else banner
            await message.answer_photo(fid, caption=caption, reply_markup=markup)
            return
        except Exception:
            pass
    await message.answer(caption, reply_markup=markup)
