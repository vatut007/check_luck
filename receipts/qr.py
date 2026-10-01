"""Разбор строки из QR-кода фискального чека — чистая функция без Django-зависимостей.

JS её не дублирует: поле «Вставить строку из QR-кода» на форме вызывает
соответствующий API-эндпоинт, который использует эту же функцию.
"""

import datetime as dt
from urllib.parse import parse_qsl

from receipts.errors import DomainError


class QrParseError(DomainError):
    """Строка из QR не разобрана или описывает чек возврата."""


def _parse_purchased_at(raw: str) -> str:
    # Формат определяется длиной строки, а не пробой вариантов: у strptime
    # %H%M%S может "съесть" короткую HHMM через бэктрекинг регулярки и
    # молча дать неверное время вместо ошибки.
    if len(raw) == 13:
        fmt = "%Y%m%dT%H%M"
    elif len(raw) == 15:
        fmt = "%Y%m%dT%H%M%S"
    else:
        raise QrParseError("Не удалось разобрать дату покупки из строки QR.")

    try:
        value = dt.datetime.strptime(raw, fmt)
    except ValueError as exc:
        raise QrParseError("Не удалось разобрать дату покупки из строки QR.") from exc
    return value.strftime("%Y-%m-%dT%H:%M")


def parse_qr_string(raw: str) -> dict:
    params = dict(parse_qsl(raw.strip(), keep_blank_values=True))

    if params.get("n") == "2":
        raise QrParseError("Это чек возврата.")

    fn = params.get("fn", "").strip()
    fd = params.get("i", "").strip()
    fp = params.get("fp", "").strip()
    t = params.get("t", "").strip()
    s = params.get("s", "").strip()

    if not all([fn, fd, fp, t, s]):
        raise QrParseError("Не удалось распознать данные чека в строке QR.")

    return {
        "fn": fn,
        "fd": fd,
        "fp": fp,
        "purchased_at": _parse_purchased_at(t),
        "amount": s.replace(",", "."),
    }
