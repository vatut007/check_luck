from decimal import Decimal

import pytest

from receipts.models import Draw, ReceiptStatus
from receipts.tests.factories import ReceiptFactory, UserFactory

pytestmark = pytest.mark.django_db

CABINET_URL = "/cabinet/"


class TestCabinetAccess:
    def test_anonymous_is_redirected_to_login(self, client):
        response = client.get(CABINET_URL)
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_empty_state_is_shown_without_receipts(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.get(CABINET_URL)

        assert response.status_code == 200
        assert "Вы не добавили еще ни одного чека" in response.content.decode()
        assert response.context["total_count"] == 0


class TestCabinetListing:
    def test_shows_only_own_receipts(self, client):
        user = UserFactory()
        other = UserFactory()
        ReceiptFactory(user=user)
        ReceiptFactory(user=other)
        client.force_login(user)

        response = client.get(CABINET_URL)

        assert response.context["total_count"] == 1

    def test_default_ordering_is_newest_first(self, client):
        user = UserFactory()
        client.force_login(user)
        older = ReceiptFactory(user=user)
        newer = ReceiptFactory(user=user)

        response = client.get(CABINET_URL)

        ids = [item["receipt"].id for item in response.context["receipts"]]
        assert ids == [newer.id, older.id]

    def test_unknown_ordering_falls_back_to_default(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.get(CABINET_URL, {"ordering": "nope"})

        assert response.context["ordering"] == "-created_at"

    def test_pagination_page_size_is_10(self, client):
        user = UserFactory()
        client.force_login(user)
        for _ in range(15):
            ReceiptFactory(user=user)

        response = client.get(CABINET_URL)

        assert len(response.context["receipts"]) == 10
        assert response.context["page_obj"].paginator.num_pages == 2

    def test_second_page_via_query_param(self, client):
        user = UserFactory()
        client.force_login(user)
        for _ in range(15):
            ReceiptFactory(user=user)

        response = client.get(CABINET_URL, {"page": 2})

        assert len(response.context["receipts"]) == 5


class TestCabinetBadgesAndInfo:
    @pytest.mark.parametrize(
        "status,label,info_contains",
        [
            (ReceiptStatus.PENDING, "В обработке", "Чек в обработке"),
            (ReceiptStatus.ACCEPTED, "Обработан", ""),
        ],
    )
    def test_badge_and_info_for_status(self, client, status, label, info_contains):
        user = UserFactory()
        client.force_login(user)
        ReceiptFactory(user=user, status=status)

        response = client.get(CABINET_URL)

        item = response.context["receipts"][0]
        assert item["badge_label"] == label
        assert item["info"] == info_contains

    def test_rejected_shows_reject_reason(self, client):
        user = UserFactory()
        client.force_login(user)
        ReceiptFactory(user=user, status=ReceiptStatus.REJECTED, reject_reason="Нечитаемое фото")

        response = client.get(CABINET_URL)

        item = response.context["receipts"][0]
        assert item["badge_label"] == "Ошибка"
        assert item["info"] == "Нечитаемое фото"

    def test_won_shows_prize_title(self, client):
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

        response = client.get(CABINET_URL)

        item = response.context["receipts"][0]
        assert item["badge_label"] == "Вы выиграли"
        assert "Сертификат 5000 ₽" in item["info"]

    def test_amount_uses_space_as_thousands_separator(self, client):
        user = UserFactory()
        client.force_login(user)
        ReceiptFactory(user=user, amount=Decimal("12000.00"))

        response = client.get(CABINET_URL)

        item = response.context["receipts"][0]
        assert item["amount_display"] == "12 000"
