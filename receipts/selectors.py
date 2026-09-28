"""Функции чтения — используются и из API, и из серверного кабинета (шаг 10)."""

from receipts.models import Receipt

ORDERING_FIELDS = {"purchased_at", "status", "amount", "created_at"}
DEFAULT_ORDERING = "-created_at"


def receipts_for_user(user, ordering=None):
    """Только чеки данного пользователя. Параметры вроде ?user=/?id= сюда не попадают —
    вызывающая сторона обязана передавать request.user, а не значение из query-параметров.
    """
    field = (ordering or "").lstrip("-")
    if field not in ORDERING_FIELDS:
        ordering = DEFAULT_ORDERING
    return Receipt.objects.filter(user=user).order_by(ordering)
