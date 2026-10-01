import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from PIL import Image

from receipts.models import Draw, Receipt, ReceiptStatus
from receipts.tests.factories import ReceiptFactory, UserFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/receipts/"
PROMO_URL = "/api/promo/"


def _payload(**overrides):
    payload = {
        "fn": "1234567890123456",
        "fd": "1",
        "fp": "1",
        "purchased_at": timezone.now().isoformat(),
        "amount": "1500.00",
    }
    payload.update(overrides)
    return payload


class TestReceiptList:
    def test_anonymous_is_rejected(self, client):
        response = client.get(LIST_URL)
        assert response.status_code in (401, 403)

    def test_returns_only_own_receipts(self, client):
        user = UserFactory()
        other = UserFactory()
        mine = ReceiptFactory(user=user)
        ReceiptFactory(user=other)
        client.force_login(user)

        response = client.get(LIST_URL)

        ids = [item["id"] for item in response.json()["results"]]
        assert ids == [mine.id]

    @pytest.mark.parametrize("param", ["user", "user_id", "id"])
    def test_foreign_filter_params_are_ignored(self, client, param):
        user = UserFactory()
        other = UserFactory()
        mine = ReceiptFactory(user=user)
        foreign = ReceiptFactory(user=other)
        client.force_login(user)

        response = client.get(LIST_URL, {param: foreign.id})

        ids = [item["id"] for item in response.json()["results"]]
        assert ids == [mine.id]

    def test_default_ordering_is_newest_first(self, client):
        user = UserFactory()
        client.force_login(user)
        older = ReceiptFactory(user=user)
        newer = ReceiptFactory(user=user)

        response = client.get(LIST_URL)

        ids = [item["id"] for item in response.json()["results"]]
        assert ids == [newer.id, older.id]

    def test_unknown_ordering_falls_back_to_default(self, client):
        user = UserFactory()
        client.force_login(user)
        older = ReceiptFactory(user=user)
        newer = ReceiptFactory(user=user)

        response = client.get(LIST_URL, {"ordering": "secret_field"})

        ids = [item["id"] for item in response.json()["results"]]
        assert ids == [newer.id, older.id]

    def test_pagination_page_size_is_10(self, client):
        user = UserFactory()
        client.force_login(user)
        for _ in range(15):
            ReceiptFactory(user=user)

        response = client.get(LIST_URL)
        data = response.json()

        assert len(data["results"]) == 10
        assert data["count"] == 15


class TestReceiptListEtag:
    def test_response_has_etag(self, client):
        user = UserFactory()
        client.force_login(user)
        ReceiptFactory(user=user)

        response = client.get(LIST_URL)

        assert response.status_code == 200
        assert response.headers.get("ETag")

    def test_matching_if_none_match_returns_304_without_body(self, client):
        user = UserFactory()
        client.force_login(user)
        ReceiptFactory(user=user)

        first = client.get(LIST_URL)
        etag = first.headers["ETag"]

        second = client.get(LIST_URL, HTTP_IF_NONE_MATCH=etag)

        assert second.status_code == 304
        assert second.content == b""

    def test_etag_changes_after_receipt_is_updated(self, client):
        user = UserFactory()
        client.force_login(user)
        receipt = ReceiptFactory(user=user)

        first = client.get(LIST_URL)
        etag = first.headers["ETag"]

        receipt.amount = Decimal("2000.00")
        receipt.save(update_fields=["amount", "updated_at"])

        second = client.get(LIST_URL, HTTP_IF_NONE_MATCH=etag)

        assert second.status_code == 200
        assert second.headers["ETag"] != etag

    def test_etag_differs_between_users(self, client):
        user = UserFactory()
        other = UserFactory()
        ReceiptFactory(user=user)
        ReceiptFactory(user=other)
        client.force_login(user)
        other_client = Client()
        other_client.force_login(other)

        response = client.get(LIST_URL)
        other_response = other_client.get(LIST_URL)

        assert response.headers["ETag"] != other_response.headers["ETag"]


class TestReceiptSerialization:
    def test_prize_title_is_empty_without_a_prize(self, client):
        user = UserFactory()
        client.force_login(user)
        ReceiptFactory(user=user, status=ReceiptStatus.ACCEPTED)

        response = client.get(LIST_URL)

        assert response.json()["results"][0]["prize_title"] == ""

    def test_prize_title_reflects_the_won_draw(self, client):
        user = UserFactory()
        client.force_login(user)
        draw = Draw.objects.create(
            title="Сертификат 5000 ₽",
            winners_count=1,
            seed="seed",
            participants_count=1,
            participants=[],
            participants_hash="hash",
            performed_by=user,
        )
        ReceiptFactory(user=user, status=ReceiptStatus.WON, prize=draw)

        response = client.get(LIST_URL)

        assert response.json()["results"][0]["prize_title"] == "Сертификат 5000 ₽"


class TestReceiptCreate:
    def test_creates_pending_receipt(self, client, promo_period):
        user = UserFactory()
        client.force_login(user)

        response = client.post(LIST_URL, data=_payload(), content_type="application/json")

        assert response.status_code == 201
        assert response.json()["status"] == ReceiptStatus.PENDING
        assert Receipt.objects.filter(user=user).count() == 1

    def test_ignores_status_from_request_body(self, client, promo_period):
        user = UserFactory()
        client.force_login(user)

        response = client.post(
            LIST_URL,
            data=_payload(status=ReceiptStatus.WON),
            content_type="application/json",
        )

        assert response.status_code == 201
        assert response.json()["status"] == ReceiptStatus.PENDING

    def test_photo_url_points_to_private_view_not_media(self, client, promo_period):
        user = UserFactory()
        client.force_login(user)
        buffer = io.BytesIO()
        Image.new("RGB", (50, 50)).save(buffer, format="JPEG")
        photo = SimpleUploadedFile("r.jpg", buffer.getvalue(), content_type="image/jpeg")

        response = client.post(LIST_URL, data={**_payload(), "photo": photo})

        assert response.status_code == 201
        body = response.json()
        assert body["photo"].startswith("/receipts/")
        assert body["photo"].endswith("/photo/")
        assert "/media/" not in body["photo"]
        assert body["photo_thumb"].endswith("/photo/?size=thumb")

    def test_duplicate_from_another_user_returns_409(self, client, promo_period):
        user = UserFactory()
        other = UserFactory()
        existing = ReceiptFactory(user=other, status=ReceiptStatus.ACCEPTED)
        client.force_login(user)

        response = client.post(
            LIST_URL,
            data=_payload(fn=existing.fn, fd=existing.fd, fp=existing.fp),
            content_type="application/json",
        )

        assert response.status_code == 409
        body = response.json()
        assert body["errors"] == {}
        assert "другим участником" in body["detail"]

    def test_invalid_field_returns_field_errors(self, client, promo_period):
        user = UserFactory()
        client.force_login(user)

        response = client.post(LIST_URL, data=_payload(fn="123"), content_type="application/json")

        assert response.status_code == 400
        assert "fn" in response.json()["errors"]

    def test_resubmitting_rejected_receipt_returns_200(self, client, promo_period):
        user = UserFactory()
        existing = ReceiptFactory(
            user=user, status=ReceiptStatus.REJECTED, reject_reason="Нечитаемое фото"
        )
        client.force_login(user)

        response = client.post(
            LIST_URL,
            data=_payload(fn=existing.fn, fd=existing.fd, fp=existing.fp),
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["status"] == ReceiptStatus.PENDING

    def test_amount_with_comma_is_accepted(self, client, promo_period):
        user = UserFactory()
        client.force_login(user)

        response = client.post(
            LIST_URL, data=_payload(amount="1500,00"), content_type="application/json"
        )

        assert response.status_code == 201


class TestPromoConfig:
    def test_requires_authentication(self, client):
        response = client.get(PROMO_URL)
        assert response.status_code in (401, 403)

    def test_returns_promo_rules(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.get(PROMO_URL)

        assert response.status_code == 200
        data = response.json()
        assert data["fn_length"] == 16
        assert data["fd_max_length"] == 10
        assert "min_amount" in data
        assert "start_date" in data and "end_date" in data
