from django.conf import settings
from django.utils.http import quote_etag
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from receipts import selectors
from receipts.api.serializers import (
    ParsedReceiptSerializer,
    ParseQrRequestSerializer,
    PromoConfigSerializer,
    ReceiptSerializer,
)
from receipts.qr import QrParseError, parse_qr_string


class ReceiptListCreateView(generics.ListCreateAPIView):
    serializer_class = ReceiptSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_scope = "receipts-write"

    def get_queryset(self):
        # Всегда только чеки текущего пользователя — параметры запроса
        # (?user=, ?user_id=, ?id=...) на выбор пользователя не влияют.
        return selectors.receipts_for_user(
            self.request.user, ordering=self.request.query_params.get("ordering")
        )

    def get_throttles(self):
        if self.request.method == "POST":
            return [ScopedRateThrottle()]
        return []

    def list(self, request, *args, **kwargs):
        etag = quote_etag(selectors.receipts_etag(request.user))
        if request.headers.get("If-None-Match") == etag:
            response = Response(status=status.HTTP_304_NOT_MODIFIED)
            response["ETag"] = etag
            return response

        response = super().list(request, *args, **kwargs)
        response["ETag"] = etag
        return response

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        created = getattr(serializer, "created", True)
        code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=code)


class PromoConfigView(APIView):
    """Правила акции для фронта — единый источник вместо констант в шаблонах и JS."""

    @extend_schema(responses=PromoConfigSerializer)
    def get(self, request):
        promo = settings.PROMO
        return Response(
            {
                "start_date": promo.start_date.isoformat(),
                "end_date": promo.end_date.isoformat(),
                "timezone": promo.tz_name,
                "min_amount": str(promo.min_amount),
                "fn_length": 16,
                "fd_max_length": 10,
                "fp_max_length": 10,
                "photo_max_mb": promo.photo_max_mb,
            }
        )


class ParseQrView(APIView):
    """Разбор строки из QR-кода — заполняет поля формы, ничего не сохраняет."""

    @extend_schema(request=ParseQrRequestSerializer, responses=ParsedReceiptSerializer)
    def post(self, request):
        serializer = ParseQrRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            data = parse_qr_string(serializer.validated_data["raw"])
        except QrParseError as exc:
            raise serializers.ValidationError({"raw": [exc.message]}) from exc

        return Response(data)
