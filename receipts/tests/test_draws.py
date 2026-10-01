import pytest

from receipts.models import Draw, ReceiptStatus
from receipts.services import DrawError, participants_hash, pick_winners, run_draw
from receipts.tests.factories import ReceiptFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestPickWinners:
    def test_same_seed_and_participants_give_same_result(self):
        participants = [[1, 10], [2, 20], [3, 30], [4, 40], [5, 50]]
        first = pick_winners(participants, seed="fixed-seed", count=2)
        second = pick_winners(participants, seed="fixed-seed", count=2)
        assert first == second

    def test_different_seed_usually_gives_different_result(self):
        participants = [[i, i * 10] for i in range(1, 21)]
        a = pick_winners(participants, seed="seed-a", count=5)
        b = pick_winners(participants, seed="seed-b", count=5)
        assert a != b

    def test_one_user_wins_at_most_once(self):
        # Один пользователь зарегистрировал несколько чеков — выиграть может не больше раза.
        participants = [[1, 100], [2, 100], [3, 100], [4, 200]]
        winners = pick_winners(participants, seed="s", count=2)
        winning_users = []
        by_receipt = dict(participants)
        for receipt_id in winners:
            winning_users.append(by_receipt[receipt_id])
        assert len(winning_users) == len(set(winning_users))

    def test_does_not_pick_more_than_requested(self):
        participants = [[i, i] for i in range(1, 11)]
        winners = pick_winners(participants, seed="s", count=3)
        assert len(winners) == 3

    def test_winners_are_a_subset_of_participants(self):
        participants = [[1, 1], [2, 2], [3, 3]]
        winners = pick_winners(participants, seed="s", count=2)
        participant_ids = {p[0] for p in participants}
        assert set(winners) <= participant_ids


class TestParticipantsHash:
    def test_same_list_gives_same_hash(self):
        participants = [[1, 10], [2, 20]]
        assert participants_hash(participants) == participants_hash(participants)

    def test_different_list_gives_different_hash(self):
        assert participants_hash([[1, 10]]) != participants_hash([[1, 11]])


class TestRunDraw:
    def test_marks_winners_and_logs_transition(self):
        staff = UserFactory(is_staff=True)
        for _ in range(3):
            ReceiptFactory(status=ReceiptStatus.ACCEPTED)

        draw = run_draw(title="Сертификат", winners_count=2, seed="fixed", actor=staff)

        assert draw.participants_count == 3
        assert draw.winners_count == 2
        winners = draw.winning_receipts.all()
        assert winners.count() == 2
        for receipt in winners:
            assert receipt.status == ReceiptStatus.WON
            log = receipt.status_logs.latest("created_at")
            assert log.from_status == ReceiptStatus.ACCEPTED
            assert log.to_status == ReceiptStatus.WON
            assert log.actor == staff

    def test_only_accepted_receipts_participate(self):
        staff = UserFactory(is_staff=True)
        accepted = ReceiptFactory(status=ReceiptStatus.ACCEPTED)
        ReceiptFactory(status=ReceiptStatus.PENDING)
        ReceiptFactory(status=ReceiptStatus.REJECTED, reject_reason="x")

        draw = run_draw(title="Приз", winners_count=1, seed="s", actor=staff)

        assert draw.participants_count == 1
        assert [receipt_id for receipt_id, _ in draw.participants] == [accepted.id]

    def test_raises_when_not_enough_accepted_receipts(self):
        staff = UserFactory(is_staff=True)
        ReceiptFactory(status=ReceiptStatus.ACCEPTED)

        with pytest.raises(DrawError, match="Недостаточно"):
            run_draw(title="Приз", winners_count=5, seed="s", actor=staff)

        assert Draw.objects.count() == 0

    def test_already_won_receipts_do_not_participate_again(self):
        staff = UserFactory(is_staff=True)
        for _ in range(2):
            ReceiptFactory(status=ReceiptStatus.ACCEPTED)
        first_draw = run_draw(title="Первый приз", winners_count=1, seed="a", actor=staff)
        won_id = first_draw.winning_receipts.first().id

        ReceiptFactory(status=ReceiptStatus.ACCEPTED)
        second_draw = run_draw(title="Второй приз", winners_count=1, seed="b", actor=staff)

        assert won_id not in [r for r, _u in second_draw.participants]

    def test_blank_title_is_rejected(self):
        staff = UserFactory(is_staff=True)
        ReceiptFactory(status=ReceiptStatus.ACCEPTED)

        with pytest.raises(DrawError, match="название"):
            run_draw(title="   ", winners_count=1, seed="s", actor=staff)

    def test_seed_is_generated_when_blank(self):
        staff = UserFactory(is_staff=True)
        ReceiptFactory(status=ReceiptStatus.ACCEPTED)

        draw = run_draw(title="Приз", winners_count=1, seed="", actor=staff)

        assert draw.seed
