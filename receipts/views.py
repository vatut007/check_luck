import datetime as dt

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from receipts import validators
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
