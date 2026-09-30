from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from receipts import validators
from receipts.api.exceptions import Conflict
from receipts.models import Receipt
from receipts.services import DuplicateReceiptError, register_receipt


class PromoConfigSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    timezone = serializers.CharField()
    min_amount = serializers.CharField()
    fn_length = serializers.IntegerField()
    fd_max_length = serializers.IntegerField()
    fp_max_length = serializers.IntegerField()
    photo_max_mb = serializers.IntegerField()


class ParseQrRequestSerializer(serializers.Serializer):
    raw = serializers.CharField()


class ParsedReceiptSerializer(serializers.Serializer):
    fn = serializers.CharField()
    fd = serializers.CharField()
    fp = serializers.CharField()
    purchased_at = serializers.CharField()
    amount = serializers.CharField()


class ReceiptSerializer(serializers.ModelSerializer):
    # Переопределены как CharField, чтобы модель проверки (validators.py) сама решала,
    # что делать с пробелами и запятой в сумме — раньше, чем DRF успеет отклонить их сам.
    fn = serializers.CharField()
    fd = serializers.CharField()
    fp = serializers.CharField()
    amount = serializers.CharField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "id",
            "fn",
            "fd",
            "fp",
            "purchased_at",
            "amount",
            "status",
            "status_display",
            "reject_reason",
            "photo",
            "photo_thumb",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "status_display",
            "reject_reason",
            "photo_thumb",
            "created_at",
            "updated_at",
        ]
        # Уникальность fn+fd+fp разбирает services.register_receipt (три разных случая
        # дубля с разными кодами ответа) — авто-UniqueTogetherValidator тут не подходит.
        validators = []

    def validate_fn(self, value: str) -> str:
        try:
            return validators.validate_fn(value)
        except validators.ValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_fd(self, value: str) -> str:
        try:
            return validators.validate_fd(value)
        except validators.ValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_fp(self, value: str) -> str:
        try:
            return validators.validate_fp(value)
        except validators.ValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_amount(self, value: str) -> Decimal:
        try:
            return validators.validate_amount(value, settings.PROMO.min_amount)
        except validators.ValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_purchased_at(self, value):
        try:
            return validators.validate_purchase_datetime(value, settings.PROMO)
        except validators.ValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def create(self, validated_data):
        user = self.context["request"].user
        try:
            receipt, created = register_receipt(
                user=user,
                fn=validated_data["fn"],
                fd=validated_data["fd"],
                fp=validated_data["fp"],
                purchased_at=validated_data["purchased_at"],
                amount=validated_data["amount"],
                photo=validated_data.get("photo"),
            )
        except DuplicateReceiptError as exc:
            raise Conflict(exc.message) from exc
        self.created = created
        return receipt
