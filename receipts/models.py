import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

validate_fn = RegexValidator(r"^\d{16}$", "ФН должен содержать ровно 16 цифр.")
validate_fd = RegexValidator(r"^\d{1,10}$", "ФД должен содержать от 1 до 10 цифр.")
validate_fp = RegexValidator(r"^\d{1,10}$", "ФП должен содержать от 1 до 10 цифр.")


class ReceiptStatus(models.TextChoices):
    PENDING = "pending", "На проверке"
    ACCEPTED = "accepted", "Принят"
    REJECTED = "rejected", "Отклонён"
    WON = "won", "Выиграл"


def receipt_photo_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"receipts/{instance.user_id}/{uuid.uuid4().hex}.{ext}"


def receipt_photo_thumb_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"receipts/{instance.user_id}/thumbs/{uuid.uuid4().hex}.{ext}"


class Draw(models.Model):
    """Розыгрыш приза среди принятых чеков. Неизменяем после создания (см. admin в шаге 15)."""

    title = models.CharField("Название приза", max_length=200)
    winners_count = models.PositiveIntegerField("Число победителей")
    seed = models.CharField("Зерно генератора", max_length=64)
    participants_count = models.PositiveIntegerField("Число участников")
    participants = models.JSONField(
        "Участники",
        help_text="Отсортированный по id чека список пар [receipt_id, user_id].",
    )
    participants_hash = models.CharField("Хэш списка участников", max_length=64)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="draws_performed",
        verbose_name="Кто провёл",
    )
    performed_at = models.DateTimeField("Когда проведён", auto_now_add=True)

    class Meta:
        verbose_name = "Розыгрыш"
        verbose_name_plural = "Розыгрыши"
        ordering = ["-performed_at"]

    def __str__(self):
        return self.title


class Receipt(models.Model):
    fn = models.CharField("ФН", max_length=16, validators=[validate_fn])
    fd = models.CharField("ФД", max_length=10, validators=[validate_fd])
    fp = models.CharField("ФП", max_length=10, validators=[validate_fp])
    purchased_at = models.DateTimeField("Дата покупки")
    amount = models.DecimalField("Сумма", max_digits=12, decimal_places=2)
    status = models.CharField(
        "Статус",
        max_length=16,
        choices=ReceiptStatus.choices,
        default=ReceiptStatus.PENDING,
    )
    prize = models.ForeignKey(
        Draw,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="winning_receipts",
        verbose_name="Выигранный розыгрыш",
    )
    reject_reason = models.TextField("Причина отказа", blank=True)
    photo = models.ImageField("Фото чека", upload_to=receipt_photo_path, null=True, blank=True)
    photo_thumb = models.ImageField(
        "Миниатюра", upload_to=receipt_photo_thumb_path, null=True, blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="receipts",
        verbose_name="Пользователь",
    )
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)
    updated_at = models.DateTimeField("Дата изменения", auto_now=True)

    class Meta:
        verbose_name = "Чек"
        verbose_name_plural = "Чеки"
        constraints = [
            models.UniqueConstraint(fields=["fn", "fd", "fp"], name="receipt_fiscal_unique"),
            # Санитарная проверка на уровне БД (сумма не может быть нулевой
            # или отрицательной), не путать с настраиваемым PROMO_MIN_AMOUNT
            # из validators.py — тот порог живёт только в .env и не может
            # быть жёстко зашит сюда, иначе понижение PROMO_MIN_AMOUNT ниже
            # старого значения привело бы к IntegrityError на каждой заявке.
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="receipt_amount_min"),
            models.CheckConstraint(
                condition=~(models.Q(status=ReceiptStatus.REJECTED) & models.Q(reject_reason="")),
                name="receipt_reject_reason_required",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="receipt_user_created_idx"),
        ]

    def __str__(self):
        return f"{self.fn}/{self.fd}/{self.fp}"


class ReceiptStatusLog(models.Model):
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="status_logs")
    from_status = models.CharField(
        "Из статуса", max_length=16, choices=ReceiptStatus.choices, blank=True
    )
    to_status = models.CharField("В статус", max_length=16, choices=ReceiptStatus.choices)
    reason = models.TextField("Причина", blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipt_status_actions",
        verbose_name="Кто изменил",
        help_text="Пусто — изменение системой (например, розыгрышем).",
    )
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "Запись истории статуса"
        verbose_name_plural = "История статусов"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.receipt_id}: {self.from_status or '—'} → {self.to_status}"
