"""Общий базовый класс для ошибок бизнес-правил приложения.

validators.ValidationError, qr.QrParseError, photos.PhotoError и ошибки
services.py (DuplicateReceiptError, InvalidTransitionError, DrawError) — это
один и тот же контракт: готовое для пользователя сообщение в `.message`,
которое вызывающая сторона кладёт прямо в ответ API или в текст под полем
формы. До этого класса каждый модуль заново объявлял одинаковый `__init__`.
"""


class DomainError(Exception):
    """Базовая ошибка бизнес-правил. Всегда несёт готовое сообщение в .message."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
