from rest_framework import exceptions
from rest_framework.views import exception_handler as drf_exception_handler


class Conflict(exceptions.APIException):
    """409 — данные валидны, но конфликтуют с текущим состоянием (см. docs/decisions/002)."""

    status_code = 409
    default_detail = "Конфликт с текущим состоянием."
    default_code = "conflict"


def exception_handler(exc, context):
    """Единый формат ошибок API: {"errors": {"field": [...]}, "detail": "..."}."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and set(data.keys()) <= {"detail"}:
        response.data = {"errors": {}, "detail": str(data.get("detail", ""))}
    else:
        errors = data if isinstance(data, dict) else {"non_field_errors": data}
        response.data = {"errors": errors, "detail": ""}
    return response
