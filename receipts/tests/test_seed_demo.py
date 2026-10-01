import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from receipts.models import Draw, Receipt, ReceiptStatus

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestSeedDemo:
    def test_creates_expected_demo_state(self):
        call_command("seed_demo")

        moderator = User.objects.get(username="moderator")
        assert moderator.is_staff
        assert moderator.is_superuser
        assert moderator.check_password("moderator")

        demo = User.objects.get(username="demo")
        assert demo.check_password("demo")
        assert not demo.is_staff

        receipts = Receipt.objects.filter(user=demo)
        assert receipts.count() == 25
        assert receipts.filter(status=ReceiptStatus.WON).count() == 1
        assert receipts.filter(status=ReceiptStatus.ACCEPTED).count() == 13
        assert receipts.filter(status=ReceiptStatus.REJECTED).count() == 7
        assert receipts.filter(status=ReceiptStatus.PENDING).count() == 4
        assert all(r.reject_reason for r in receipts.filter(status=ReceiptStatus.REJECTED))

        won = receipts.get(status=ReceiptStatus.WON)
        assert won.prize is not None
        assert won.prize.winning_receipts.filter(pk=won.pk).exists()

        stranger = User.objects.get(username="stranger_demo")
        stranger_receipts = Receipt.objects.filter(user=stranger)
        assert stranger_receipts.count() == 2
        demo_fns = set(receipts.values_list("fn", flat=True))
        assert demo_fns.isdisjoint(set(stranger_receipts.values_list("fn", flat=True)))

        participants = User.objects.filter(username__startswith="participant")
        assert participants.count() == 15
        for user in participants:
            assert Receipt.objects.filter(user=user).exists()
        assert Draw.objects.filter(title__icontains="Еженедельный розыгрыш").exists()

    def test_running_twice_does_not_duplicate_anything(self):
        call_command("seed_demo")
        receipts_after_first = Receipt.objects.count()
        users_after_first = User.objects.count()
        draws_after_first = Draw.objects.count()

        call_command("seed_demo")

        assert Receipt.objects.count() == receipts_after_first
        assert User.objects.count() == users_after_first
        assert Draw.objects.count() == draws_after_first
