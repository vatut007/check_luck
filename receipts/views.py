import datetime as dt

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.formats import number_format

from receipts import selectors, validators
from receipts.models import Receipt, ReceiptStatus
from receipts.photos import PhotoError, validate_photo
from receipts.services import DuplicateReceiptError, register_receipt


def home(request):
    return render(request, "receipts/home.html")


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("receipts:cabinet")
    else:
        form = UserCreationForm()

    return render(request, "registration/signup.html", {"form": form})


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

        photo = request.FILES.get("photo")
        if photo is not None:
            try:
                validate_photo(photo, promo.photo_max_mb)
            except PhotoError as exc:
                errors["photo"] = exc.message

        if not errors:
            try:
                register_receipt(user=request.user, photo=photo, **cleaned)
            except DuplicateReceiptError as exc:
                errors["general"] = exc.message
            else:
                # PRG: без этого редиректа F5 после успешной отправки
                # повторно отправляет ту же форму (POST) и чек регистрируется
                # ещё раз / показывает "уже зарегистрирован".
                return redirect("receipts:receipt-form-success")

    return render(
        request,
        "receipts/receipt_form.html",
        {"promo": promo, "values": values, "errors": errors},
    )


@login_required
def receipt_form_success(request):
    return render(request, "receipts/receipt_form_success.html")


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


def _format_amount(amount):
    # Копейки показываем только когда они не нулевые — "1 500 ₽" вместо
    # "1 500,00 ₽", но "1 234,56 ₽", если сумма действительно не круглая.
    decimal_pos = 0 if amount == amount.to_integral_value() else 2
    formatted = number_format(amount, decimal_pos=decimal_pos, force_grouping=True)
    return formatted.replace("\xa0", " ")


def _present_receipt(receipt):
    badge = STATUS_BADGES[receipt.status]
    return {
        "receipt": receipt,
        "badge_label": badge["label"],
        "badge_modifier": badge["modifier"],
        "amount_display": _format_amount(receipt.amount),
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
            "has_pending": any(r.status == ReceiptStatus.PENDING for r in page_obj.object_list),
        },
    )


@login_required
def receipt_photo(request, pk):
    """Фото чека не отдаётся из /media/ напрямую — только тому, кому принадлежит чек."""
    receipt = get_object_or_404(Receipt, pk=pk)
    if receipt.user_id != request.user.id and not request.user.is_staff:
        raise Http404

    image_field = receipt.photo_thumb if request.GET.get("size") == "thumb" else receipt.photo
    if not image_field:
        raise Http404

    return FileResponse(image_field.open("rb"))
