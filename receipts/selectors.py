"""Функции чтения — используются и из API, и из серверного кабинета."""

import hashlib

from django.db.models import Count, Max

from receipts.models import Receipt

ORDERING_FIELDS = {"purchased_at", "status", "amount", "created_at"}
DEFAULT_ORDERING = "-created_at"


def resolve_ordering(ordering):
    """Белый список сортировки: неизвестное или пустое значение → сортировка по умолчанию."""
    field = (ordering or "").lstrip("-")
    if field not in ORDERING_FIELDS:
        return DEFAULT_ORDERING
    return ordering


def receipts_for_user(user, ordering=None):
    """Только чеки данного пользователя. Параметры вроде ?user=/?id= сюда не попадают —
    вызывающая сторона обязана передавать request.user, а не значение из query-параметров.
    """
    return (
        Receipt.objects.filter(user=user)
        .select_related("prize")
        .order_by(resolve_ordering(ordering))
    )


def receipts_etag(user) -> str:
    """ETag из max(updated_at) и количества чеков пользователя — для polling с If-None-Match."""
    agg = Receipt.objects.filter(user=user).aggregate(
        last_updated=Max("updated_at"), total=Count("id")
    )
    last_updated = agg["last_updated"].isoformat() if agg["last_updated"] else ""
    raw = f"{user.pk}:{agg['total']}:{last_updated}"
    return hashlib.sha256(raw.encode()).hexdigest()
