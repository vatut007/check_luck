import io

import pytest
from django.core.files.base import ContentFile
from PIL import Image

from receipts.tests.factories import ReceiptFactory, UserFactory

pytestmark = pytest.mark.django_db


def _jpeg_bytes(color="red"):
    buffer = io.BytesIO()
    Image.new("RGB", (50, 50), color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _receipt_with_photo(**kwargs):
    receipt = ReceiptFactory(**kwargs)
    receipt.photo = ContentFile(_jpeg_bytes("red"), name="photo.jpg")
    receipt.photo_thumb = ContentFile(_jpeg_bytes("blue"), name="thumb.jpg")
    receipt.save(update_fields=["photo", "photo_thumb"])
    return receipt


def _photo_url(receipt, size=None):
    url = f"/receipts/{receipt.id}/photo/"
    return f"{url}?size={size}" if size else url


class TestReceiptPhotoView:
    def test_anonymous_is_redirected_to_login(self, client):
        receipt = _receipt_with_photo()
        response = client.get(_photo_url(receipt))
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_owner_can_view_own_photo(self, client):
        user = UserFactory()
        receipt = _receipt_with_photo(user=user)
        client.force_login(user)

        response = client.get(_photo_url(receipt))

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == _jpeg_bytes("red")

    def test_other_user_gets_404(self, client):
        owner = UserFactory()
        other = UserFactory()
        receipt = _receipt_with_photo(user=owner)
        client.force_login(other)

        response = client.get(_photo_url(receipt))

        assert response.status_code == 404

    def test_staff_can_view_any_photo(self, client):
        owner = UserFactory()
        staff = UserFactory(is_staff=True)
        receipt = _receipt_with_photo(user=owner)
        client.force_login(staff)

        response = client.get(_photo_url(receipt))

        assert response.status_code == 200

    def test_missing_receipt_is_404(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.get("/receipts/999999/photo/")

        assert response.status_code == 404

    def test_receipt_without_photo_is_404(self, client):
        user = UserFactory()
        receipt = ReceiptFactory(user=user)
        client.force_login(user)

        response = client.get(_photo_url(receipt))

        assert response.status_code == 404

    def test_thumb_query_param_serves_thumbnail(self, client):
        user = UserFactory()
        receipt = _receipt_with_photo(user=user)
        client.force_login(user)

        response = client.get(_photo_url(receipt, size="thumb"))

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == _jpeg_bytes("blue")
