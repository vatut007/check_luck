"""Проверка и обработка фото чека — по содержимому файла, а не по расширению."""

import io

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from receipts.errors import DomainError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
THUMBNAIL_SIZE = (104, 104)
_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


class PhotoError(DomainError):
    """Фото не прошло проверку содержимого или размера."""


def validate_photo(file, max_mb: int) -> None:
    max_bytes = max_mb * 1024 * 1024
    if file.size > max_bytes:
        raise PhotoError(f"Размер фото не должен превышать {max_mb} МБ.")

    file.seek(0)
    try:
        image = Image.open(file)
        image.verify()
    except Exception as exc:
        raise PhotoError("Файл повреждён или не является изображением.") from exc
    finally:
        file.seek(0)

    # verify() выгружает файл из Image — для проверки формата открываем заново.
    image = Image.open(file)
    if image.format not in ALLOWED_FORMATS:
        raise PhotoError("Допустимые форматы фото: JPEG, PNG, WEBP.")
    file.seek(0)


def _save_image(image: Image.Image, fmt: str) -> ContentFile:
    buffer = io.BytesIO()
    save_kwargs = {"format": fmt}
    if fmt in ("JPEG", "WEBP"):
        save_kwargs["quality"] = 90
    image.save(buffer, **save_kwargs)
    return ContentFile(buffer.getvalue(), name=f"receipt.{_EXTENSIONS[fmt]}")


def process_photo(file) -> tuple[ContentFile, ContentFile]:
    """Возвращает (фото без EXIF, миниатюра 104×104).

    Вызывающая сторона обязана предварительно вызвать validate_photo().
    EXIF (в нём бывают GPS-координаты) убирается пересборкой изображения
    из чистых пиксельных данных — у новой картинки просто нет .info с метаданными.
    """
    file.seek(0)
    image = Image.open(file)
    image.load()
    fmt = image.format or "JPEG"

    # exif_transpose() должен отработать до того, как EXIF исчезнет вместе
    # с тегом ориентации — иначе портретное фото с телефона ложится набок.
    image = ImageOps.exif_transpose(image)

    if image.mode == "P":
        # frombytes() на "P" кладёт в пиксели индексы палитры, а не цвета —
        # без неё и без конвертации в RGB результат превращается в чёрный
        # квадрат. convert("RGBA" для прозрачных PNG, иначе "RGB") печёт
        # палитру в реальные цвета перед пересборкой.
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")

    clean_image = Image.frombytes(image.mode, image.size, image.tobytes())
    cleaned = _save_image(clean_image, fmt)

    thumb_image = clean_image.copy()
    thumb_image.thumbnail(THUMBNAIL_SIZE)
    thumbnail = _save_image(thumb_image, fmt)

    return cleaned, thumbnail
