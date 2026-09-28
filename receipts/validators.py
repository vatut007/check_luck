"""Чистые функции проверки данных чека — без зависимостей от Django ORM/settings.

Каждая функция принимает уже распарсенное значение и либо возвращает его
в очищенном виде, либо бросает ValidationError с понятным пользователю текстом.
"""

import datetime as dt
import re
from decimal import Decimal, InvalidOperation

from config.promo import PromoConfig


class ValidationError(Exception):
    """Ошибка валидации одного поля чека."""


_FN_RE = re.compile(r"^\d{16}$")
_FD_RE = re.compile(r"^\d{1,10}$")
_FP_RE = re.compile(r"^\d{1,10}$")

# Максимальная разница часовых поясов в РФ (Калининград UTC+2 — Камчатка UTC+12) плюс запас.
FUTURE_TOLERANCE = dt.timedelta(hours=14)


def validate_fn(value: str) -> str:
    value = value.strip()
    if not _FN_RE.match(value):
        raise ValidationError("ФН должен содержать ровно 16 цифр.")
    return value


def validate_fd(value: str) -> str:
    value = value.strip()
    if not _FD_RE.match(value):
        raise ValidationError("ФД должен содержать от 1 до 10 цифр.")
    return value


def validate_fp(value: str) -> str:
    value = value.strip()
    if not _FP_RE.match(value):
        raise ValidationError("ФП должен содержать от 1 до 10 цифр.")
    return value


def validate_amount(value: str | Decimal, min_amount: Decimal) -> Decimal:
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Некорректная сумма.") from exc

    if amount <= 0:
        raise ValidationError("Сумма должна быть положительной.")
    if amount.as_tuple().exponent < -2:
        raise ValidationError("Сумма — не более двух знаков после запятой.")
    if amount < min_amount:
        raise ValidationError(f"Сумма чека должна быть не меньше {min_amount} ₽.")
    return amount


def validate_purchase_datetime(
    value: dt.datetime, promo: PromoConfig, *, now: dt.datetime | None = None
) -> dt.datetime:
    """Время на чеке не несёт часового пояса, поэтому не конвертируется — см. docs/decisions/001."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=promo.timezone)

    now = now or dt.datetime.now(dt.UTC)
    if value > now + FUTURE_TOLERANCE:
        raise ValidationError("Дата покупки не может быть в будущем.")

    purchase_date = value.astimezone(promo.timezone).date()
    if not (promo.start_date <= purchase_date <= promo.end_date):
        raise ValidationError(
            f"Акция проходит с {promo.start_date:%d.%m.%Y} по {promo.end_date:%d.%m.%Y}."
        )
    return value
