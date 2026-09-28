import threading
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

from receipts.models import ReceiptStatus
from receipts.services import (
    DuplicateReceiptError,
    InvalidTransitionError,
    moderate_receipt,
    register_receipt,
)
from receipts.tests.factories import ReceiptFactory, UserFactory

pytestmark = pytest.mark.django_db


def _receipt_kwargs(**overrides):
    kwargs = {
        "fn": "1234567890123456",
        "fd": "1",
        "fp": "1",
        "purchased_at": timezone.now(),
        "amount": Decimal("1500.00"),
    }
    kwargs.update(overrides)
    return kwargs


class TestRegisterReceipt:
    def test_creates_pending_receipt_with_log(self):
        user = UserFactory()

        receipt, created = register_receipt(user=user, **_receipt_kwargs())

        assert created is True
        assert receipt.status == ReceiptStatus.PENDING
        log = receipt.status_logs.get()
        assert log.from_status == ""
        assert log.to_status == ReceiptStatus.PENDING
        assert log.actor == user

    @pytest.mark.parametrize(
        "status", [ReceiptStatus.PENDING, ReceiptStatus.ACCEPTED, ReceiptStatus.WON]
    )
    def test_own_duplicate_raises_conflict(self, status):
        user = UserFactory()
        existing = ReceiptFactory(user=user, status=status)

        with pytest.raises(DuplicateReceiptError) as exc_info:
            register_receipt(
                user=user,
                **_receipt_kwargs(fn=existing.fn, fd=existing.fd, fp=existing.fp),
            )

        assert "другим участником" not in str(exc_info.value)

    def test_foreign_duplicate_raises_conflict(self):
        owner = UserFactory()
        other = UserFactory()
        existing = ReceiptFactory(user=owner, status=ReceiptStatus.ACCEPTED)

        with pytest.raises(DuplicateReceiptError) as exc_info:
            register_receipt(
                user=other,
                **_receipt_kwargs(fn=existing.fn, fd=existing.fd, fp=existing.fp),
            )

        assert "другим участником" in str(exc_info.value)

    def test_resubmitting_rejected_receipt_returns_to_pending(self):
        user = UserFactory()
        existing = ReceiptFactory(
            user=user, status=ReceiptStatus.REJECTED, reject_reason="Нечитаемое фото"
        )
        new_amount = Decimal("2500.00")

        receipt, created = register_receipt(
            user=user,
            **_receipt_kwargs(fn=existing.fn, fd=existing.fd, fp=existing.fp, amount=new_amount),
        )

        assert created is False
        assert receipt.pk == existing.pk
        assert receipt.status == ReceiptStatus.PENDING
        assert receipt.reject_reason == ""
        assert receipt.amount == new_amount
        log = receipt.status_logs.latest("created_at")
        assert log.from_status == ReceiptStatus.REJECTED
        assert log.to_status == ReceiptStatus.PENDING

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_registration_yields_one_success_one_conflict(self):
        user_a = UserFactory()
        user_b = UserFactory()
        results = []
        barrier = threading.Barrier(2)

        def attempt(user):
            barrier.wait()
            try:
                register_receipt(
                    user=user,
                    **_receipt_kwargs(fn="9999999999999999", fd="42", fp="42"),
                )
                results.append("ok")
            except DuplicateReceiptError:
                results.append("conflict")
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(u,)) for u in (user_a, user_b)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(results) == ["conflict", "ok"]


class TestModerateReceipt:
    def test_accept_pending(self):
        staff = UserFactory()
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        result = moderate_receipt(receipt=receipt, actor=staff, new_status=ReceiptStatus.ACCEPTED)

        assert result.status == ReceiptStatus.ACCEPTED
        log = receipt.status_logs.latest("created_at")
        assert log.from_status == ReceiptStatus.PENDING
        assert log.to_status == ReceiptStatus.ACCEPTED
        assert log.actor == staff

    def test_reject_requires_non_empty_reason(self):
        staff = UserFactory()
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        with pytest.raises(InvalidTransitionError):
            moderate_receipt(
                receipt=receipt, actor=staff, new_status=ReceiptStatus.REJECTED, reason="   "
            )

    def test_reject_with_reason(self):
        staff = UserFactory()
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        result = moderate_receipt(
            receipt=receipt,
            actor=staff,
            new_status=ReceiptStatus.REJECTED,
            reason="Нечитаемое фото",
        )

        assert result.status == ReceiptStatus.REJECTED
        assert result.reject_reason == "Нечитаемое фото"

    def test_cannot_moderate_non_pending_receipt(self):
        staff = UserFactory()
        receipt = ReceiptFactory(status=ReceiptStatus.ACCEPTED)

        with pytest.raises(InvalidTransitionError):
            moderate_receipt(
                receipt=receipt, actor=staff, new_status=ReceiptStatus.REJECTED, reason="x"
            )

    def test_cannot_set_won_directly(self):
        staff = UserFactory()
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        with pytest.raises(InvalidTransitionError):
            moderate_receipt(receipt=receipt, actor=staff, new_status=ReceiptStatus.WON)
