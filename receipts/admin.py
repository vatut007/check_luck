import csv

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from receipts.models import Receipt, ReceiptStatus, ReceiptStatusLog
from receipts.services import InvalidTransitionError, moderate_receipt

STAFF_SELECTABLE_STATUSES = [ReceiptStatus.PENDING, ReceiptStatus.ACCEPTED, ReceiptStatus.REJECTED]


class ReceiptStatusLogInline(admin.TabularInline):
    model = ReceiptStatusLog
    extra = 0
    can_delete = False
    fields = ["from_status", "to_status", "reason", "actor", "created_at"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ReceiptAdminForm(forms.ModelForm):
    class Meta:
        model = Receipt
        fields = ["status", "reject_reason"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Статус won ставится только розыгрышем — модератор физически не может его выбрать.
        if self.instance.pk and self.instance.status == ReceiptStatus.WON:
            self.fields["status"].disabled = True
        else:
            self.fields["status"].choices = [
                choice for choice in ReceiptStatus.choices if choice[0] in STAFF_SELECTABLE_STATUSES
            ]

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk:
            return cleaned

        new_status = cleaned.get("status")
        original_status = Receipt.objects.get(pk=self.instance.pk).status
        if new_status == original_status:
            return cleaned

        reason = (cleaned.get("reject_reason") or "").strip()
        if original_status != ReceiptStatus.PENDING:
            label = dict(ReceiptStatus.choices).get(original_status, original_status)
            raise forms.ValidationError({"status": f"Чек в статусе «{label}» уже промодерирован."})
        if new_status == ReceiptStatus.REJECTED and not reason:
            raise forms.ValidationError({"reject_reason": "Для отказа нужно указать причину."})
        return cleaned


@admin.action(description="Принять выбранные чеки")
def accept_selected(modeladmin, request, queryset):
    accepted = 0
    for receipt in queryset.filter(status=ReceiptStatus.PENDING):
        try:
            moderate_receipt(receipt=receipt, actor=request.user, new_status=ReceiptStatus.ACCEPTED)
            accepted += 1
        except InvalidTransitionError:
            continue
    skipped = queryset.exclude(status=ReceiptStatus.PENDING).count()
    modeladmin.message_user(
        request, f"Принято: {accepted}. Пропущено (не «на проверке»): {skipped}."
    )


@admin.action(description="Отклонить выбранные чеки")
def reject_selected(modeladmin, request, queryset):
    if request.POST.get("apply"):
        reason = request.POST.get("reason", "").strip()
        if not reason:
            modeladmin.message_user(request, "Укажите причину отказа.", level=messages.ERROR)
        else:
            rejected = 0
            for receipt in queryset.filter(status=ReceiptStatus.PENDING):
                moderate_receipt(
                    receipt=receipt,
                    actor=request.user,
                    new_status=ReceiptStatus.REJECTED,
                    reason=reason,
                )
                rejected += 1
            skipped = queryset.exclude(status=ReceiptStatus.PENDING).count()
            modeladmin.message_user(
                request, f"Отклонено: {rejected}. Пропущено (не «на проверке»): {skipped}."
            )
            return None

    return render(
        request,
        "admin/receipts/receipt/reject_confirmation.html",
        {
            "receipts": queryset,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            "opts": modeladmin.model._meta,
        },
    )


class Echo:
    """Псевдо-файл для csv.writer: writerow() пишет сюда и возвращает записанную строку,
    которую генератор сразу отдаёт в StreamingHttpResponse."""

    def write(self, value):
        return value


@admin.action(description="Выгрузить принятые в CSV")
def export_accepted_csv(modeladmin, request, queryset):
    accepted = queryset.filter(status=ReceiptStatus.ACCEPTED).select_related("user")

    def rows():
        yield "﻿"  # BOM, чтобы русский Excel открыл файл без кракозябр
        writer = csv.writer(Echo(), delimiter=";")
        yield writer.writerow(
            ["ID", "Пользователь", "ФН", "ФД", "ФП", "Сумма", "Дата покупки", "Дата регистрации"]
        )
        for receipt in accepted.iterator():
            yield writer.writerow(
                [
                    receipt.id,
                    receipt.user.username,
                    receipt.fn,
                    receipt.fd,
                    receipt.fp,
                    str(receipt.amount),
                    receipt.purchased_at.strftime("%d.%m.%Y %H:%M"),
                    receipt.created_at.strftime("%d.%m.%Y %H:%M"),
                ]
            )

    filename = f"receipts_accepted_{timezone.localdate():%Y-%m-%d}.csv"
    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    form = ReceiptAdminForm
    actions = [accept_selected, reject_selected, export_accepted_csv]

    list_display = [
        "id",
        "user",
        "fn",
        "fd",
        "amount",
        "purchased_at",
        "status",
        "created_at",
        "has_photo",
    ]
    list_filter = ["status", "created_at", "prize"]
    search_fields = ["fn", "fd", "fp", "user__username", "user__email"]
    inlines = [ReceiptStatusLogInline]

    fields = [
        "user",
        "fn",
        "fd",
        "fp",
        "purchased_at",
        "amount",
        "photo_preview",
        "status",
        "reject_reason",
        "prize",
        "created_at",
        "updated_at",
    ]
    readonly_fields = [
        "fn",
        "fd",
        "fp",
        "purchased_at",
        "amount",
        "user",
        "photo_preview",
        "prize",
        "created_at",
        "updated_at",
    ]

    @admin.display(description="Фото", boolean=True)
    def has_photo(self, obj):
        return bool(obj.photo)

    @admin.display(description="Фото")
    def photo_preview(self, obj):
        if not obj.photo:
            return "—"
        url = reverse("receipts:receipt-photo", args=[obj.pk])
        return format_html('<img src="{}" style="max-height: 200px">', url)

    def save_model(self, request, obj, form, change):
        if not change or "status" not in form.changed_data:
            super().save_model(request, obj, form, change)
            return

        moderate_receipt(
            receipt=Receipt.objects.get(pk=obj.pk),
            actor=request.user,
            new_status=obj.status,
            reason=obj.reject_reason,
        )
