import pytest
from django.urls import reverse
from django.utils import timezone

from receipts.models import Receipt, ReceiptStatus
from receipts.tests.factories import ReceiptFactory, UserFactory

pytestmark = pytest.mark.django_db

FORM_URL = "/receipts/new/"


def _payload(**overrides):
    payload = {
        "fn": "1234567890123456",
        "fd": "1",
        "fp": "1",
        "purchased_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        "amount": "1500.00",
    }
    payload.update(overrides)
    return payload


class TestReceiptFormView:
    def test_anonymous_is_redirected_to_login(self, client):
        response = client.get(FORM_URL)
        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))

    def test_get_renders_empty_form(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.get(FORM_URL)

        assert response.status_code == 200
        assert b'name="fn"' in response.content

    def test_valid_post_creates_receipt_and_shows_success(self, client, promo_period):
        user = UserFactory()
        client.force_login(user)

        response = client.post(FORM_URL, data=_payload())

        assert response.status_code == 200
        assert "Чек отправлен на проверку" in response.content.decode()
        receipt = Receipt.objects.get(user=user)
        assert receipt.status == ReceiptStatus.PENDING

    def test_invalid_fn_rerenders_form_with_field_error(self, client, promo_period):
        user = UserFactory()
        client.force_login(user)

        response = client.post(FORM_URL, data=_payload(fn="123"))

        assert response.status_code == 200
        assert response.context["errors"]["fn"]
        assert Receipt.objects.filter(user=user).count() == 0

    def test_duplicate_shows_general_error(self, client, promo_period):
        user = UserFactory()
        other = UserFactory()
        existing = ReceiptFactory(user=other, status=ReceiptStatus.ACCEPTED)
        client.force_login(user)

        response = client.post(
            FORM_URL,
            data=_payload(fn=existing.fn, fd=existing.fd, fp=existing.fp),
        )

        assert response.status_code == 200
        assert "другим участником" in response.context["errors"]["general"]

    def test_status_cannot_be_injected_via_post(self, client, promo_period):
        user = UserFactory()
        client.force_login(user)

        response = client.post(FORM_URL, data=_payload(status=ReceiptStatus.WON))

        assert response.status_code == 200
        receipt = Receipt.objects.get(user=user)
        assert receipt.status == ReceiptStatus.PENDING
