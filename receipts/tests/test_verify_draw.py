from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from receipts.models import ReceiptStatus
from receipts.services import run_draw
from receipts.tests.factories import ReceiptFactory, UserFactory

pytestmark = pytest.mark.django_db


def _run(draw_id):
    out = StringIO()
    call_command("verify_draw", draw_id, stdout=out)
    return out.getvalue()


class TestVerifyDraw:
    def test_honest_draw_reports_ok(self):
        staff = UserFactory(is_staff=True)
        for _ in range(3):
            ReceiptFactory(status=ReceiptStatus.ACCEPTED)
        draw = run_draw(title="Приз", winners_count=2, seed="s", actor=staff)

        output = _run(draw.id)

        assert "OK" in output

    def test_missing_draw_raises_command_error(self):
        with pytest.raises(CommandError, match="не найден"):
            call_command("verify_draw", 999999, stderr=StringIO())

    def test_tampered_participants_list_is_detected(self):
        staff = UserFactory(is_staff=True)
        for _ in range(3):
            ReceiptFactory(status=ReceiptStatus.ACCEPTED)
        draw = run_draw(title="Приз", winners_count=2, seed="s", actor=staff)

        tampered = [[9999, 9999], *draw.participants[1:]]
        draw.participants = tampered
        draw.save(update_fields=["participants"])

        with pytest.raises(CommandError, match="не прошёл проверку"):
            call_command("verify_draw", draw.id, stderr=StringIO())

    def test_tampered_winner_is_detected(self):
        staff = UserFactory(is_staff=True)
        receipts = [ReceiptFactory(status=ReceiptStatus.ACCEPTED) for _ in range(3)]
        draw = run_draw(title="Приз", winners_count=1, seed="s", actor=staff)

        actual_winner = draw.winning_receipts.get()
        other = next(r for r in receipts if r.id != actual_winner.id)

        actual_winner.status = ReceiptStatus.ACCEPTED
        actual_winner.prize = None
        actual_winner.save(update_fields=["status", "prize"])
        other.status = ReceiptStatus.WON
        other.prize = draw
        other.save(update_fields=["status", "prize"])

        with pytest.raises(CommandError, match="не прошёл проверку"):
            call_command("verify_draw", draw.id, stderr=StringIO())
