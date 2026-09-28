import datetime as dt

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render

from receipts import selectors, validators
from receipts.models import ReceiptStatus
from receipts.services import DuplicateReceiptError, register_receipt


def home(request):
    return render(request, "receipts/home.html")


FIELD_LABELS_TO_VALIDATORS = {
    "fn": validators.validate_fn,
    "fd": validators.validate_fd,
    "fp": validators.validate_fp,
}


@login_required
def receipt_form(request):
    promo = settings.PROMO
    values = {"fn": "", "fd": "", "fp": "", "purchased_at": "", "amount": ""}
    errors = {}
    success = False

    if request.method == "POST":
        values = {name: request.POST.get(name, "") for name in values}
        cleaned = {}

        for field, validate in FIELD_LABELS_TO_VALIDATORS.items():
            try:
                cleaned[field] = validate(values[field])
            except validators.ValidationError as exc:
                errors[field] = str(exc)

        try:
            cleaned["amount"] = validators.validate_amount(values["amount"], promo.min_amount)
        except validators.ValidationError as exc:
            errors["amount"] = str(exc)

        try:
            naive = dt.datetime.strptime(values["purchased_at"], "%Y-%m-%dT%H:%M")
        except ValueError:
            errors["purchased_at"] = "Введите корректную дату покупки."
        else:
            try:
                cleaned["purchased_at"] = validators.validate_purchase_datetime(
                    naive.replace(tzinfo=promo.timezone), promo
                )
            except validators.ValidationError as exc:
                errors["purchased_at"] = str(exc)

        if not errors:
            try:
                register_receipt(user=request.user, photo=request.FILES.get("photo"), **cleaned)
                success = True
            except DuplicateReceiptError as exc:
                errors["general"] = exc.message

    return render(
        request,
        "receipts/receipt_form.html",
        {"promo": promo, "values": values, "errors": errors, "success": success},
    )


SORTABLE_COLUMNS = [
    ("purchased_at", "Дата покупки"),
    ("status", "Статус"),
    ("amount", "Сумма чека"),
    ("created_at", "Дата регистрации"),
]

STATUS_BADGES = {
    ReceiptStatus.PENDING: {"label": "В обработке", "modifier": "badge--pending"},
    ReceiptStatus.ACCEPTED: {"label": "Обработан", "modifier": "badge--accepted"},
    ReceiptStatus.REJECTED: {"label": "Ошибка", "modifier": "badge--rejected"},
    ReceiptStatus.WON: {"label": "Вы выиграли", "modifier": "badge--won"},
}


def _receipt_info_text(receipt):
    if receipt.status == ReceiptStatus.PENDING:
        return "Чек в обработке"
    if receipt.status == ReceiptStatus.REJECTED:
        return receipt.reject_reason
    if receipt.status == ReceiptStatus.WON:
        prize_title = receipt.prize.title if receipt.prize_id else ""
        return f"Поздравляем, ваш чек выиграл! {prize_title}".strip()
    return ""


def _present_receipt(receipt):
    badge = STATUS_BADGES[receipt.status]
    return {
        "receipt": receipt,
        "badge_label": badge["label"],
        "badge_modifier": badge["modifier"],
        "amount_display": f"{receipt.amount:,.0f}".replace(",", " "),
        "info": _receipt_info_text(receipt),
    }


def _sort_columns(effective_ordering):
    columns = []
    for field, label in SORTABLE_COLUMNS:
        if effective_ordering == field:
            next_ordering, active, direction = f"-{field}", True, "asc"
        elif effective_ordering == f"-{field}":
            next_ordering, active, direction = field, True, "desc"
        else:
            next_ordering, active, direction = field, False, None
        columns.append(
            {
                "field": field,
                "label": label,
                "ordering": next_ordering,
                "active": active,
                "direction": direction,
            }
        )
    return columns


@login_required
def cabinet(request):
    ordering = selectors.resolve_ordering(request.GET.get("ordering"))
    queryset = selectors.receipts_for_user(request.user, ordering=ordering)

    paginator = Paginator(queryset, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "receipts/cabinet.html",
        {
            "page_obj": page_obj,
            "elided_pages": paginator.get_elided_page_range(
                page_obj.number, on_each_side=2, on_ends=1
            ),
            "ordering": ordering,
            "sort_columns": _sort_columns(ordering),
            "receipts": [_present_receipt(r) for r in page_obj.object_list],
            "total_count": paginator.count,
        },
    )
