import pytest

from receipts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PARSE_QR_URL = "/api/receipts/parse-qr/"


class TestParseQrView:
    def test_anonymous_is_rejected(self, client):
        response = client.post(PARSE_QR_URL, data={"raw": "t=20261015T1830&s=1.00&fn=1&i=1&fp=1"})
        assert response.status_code in (401, 403)

    def test_valid_string_returns_form_fields(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.post(
            PARSE_QR_URL,
            data={"raw": "t=20261015T1830&s=1234.56&fn=9999078900004312&i=12345&fp=1234567890&n=1"},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json() == {
            "fn": "9999078900004312",
            "fd": "12345",
            "fp": "1234567890",
            "purchased_at": "2026-10-15T18:30",
            "amount": "1234.56",
        }

    def test_refund_receipt_returns_field_error(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.post(
            PARSE_QR_URL,
            data={"raw": "t=20261015T1830&s=1.00&fn=1&i=1&fp=1&n=2"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "возврата" in response.json()["errors"]["raw"][0]

    def test_missing_raw_field_is_a_validation_error(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.post(PARSE_QR_URL, data={}, content_type="application/json")

        assert response.status_code == 400
        assert "raw" in response.json()["errors"]
