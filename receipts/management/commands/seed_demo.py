"""Демо-данные для ревью: модератор, обычные пользователи, чеки во всех статусах
и проведённый розыгрыш. Команда идемпотентна — повторный запуск ничего не дублирует.
"""

import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from receipts.models import Draw, Receipt, ReceiptStatus, ReceiptStatusLog
from receipts.services import run_draw

User = get_user_model()

REJECT_REASONS = [
    "Нечитаемое фото чека",
    "Сумма меньше минимальной по акции",
    "Чек не найден в ФНС",
    "Указан неверный номер ФН",
    "Дубликат уже зарегистрированного чека",
    "Чек оформлен за пределами периода акции",
    "Повреждённое изображение чека",
]

BULK_DRAW_TITLE = "Еженедельный розыгрыш: сертификат 3000 ₽"


def _fn(group: str, index: int) -> str:
    return f"9{group}{index:014d}"


class Command(BaseCommand):
    help = "Создаёт демо-пользователей, чеки во всех статусах и проведённый розыгрыш."

    def handle(self, *args, **options):
        moderator = self._get_or_create_user("moderator", "moderator", is_staff=True)
        demo = self._get_or_create_user("demo", "demo")
        stranger = self._get_or_create_user("stranger_demo", "stranger_demo")

        # Оба розыгрыша проводятся первыми, пока в системе нет других принятых
        # чеков — иначе run_draw() (честно) захватит в пул вообще всё принятое,
        # включая чеки demo/stranger ниже, и "лишние" из них тоже выиграют.
        self._seed_demo_win(demo, moderator)
        self._seed_bulk_users_and_draw(moderator)

        self._seed_demo_variety(demo, moderator)
        self._seed_stranger(stranger, moderator)

        self.stdout.write(self.style.SUCCESS("Демо-данные готовы."))

    def _get_or_create_user(self, username, password, is_staff=False):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@example.com", "is_staff": is_staff},
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user

    def _seed_receipt(self, user, *, fn, amount, days_ago, status, reject_reason="", actor=None):
        receipt, created = Receipt.objects.get_or_create(
            fn=fn,
            fd="1",
            fp="1",
            defaults={
                "user": user,
                "amount": Decimal(amount),
                "purchased_at": timezone.now() - dt.timedelta(days=days_ago),
                "status": ReceiptStatus.PENDING,
            },
        )
        if not created:
            return receipt

        ReceiptStatusLog.objects.create(
            receipt=receipt, from_status="", to_status=ReceiptStatus.PENDING, actor=user
        )
        if status != ReceiptStatus.PENDING:
            receipt.status = status
            receipt.reject_reason = reject_reason
            receipt.save(update_fields=["status", "reject_reason"])
            ReceiptStatusLog.objects.create(
                receipt=receipt,
                from_status=ReceiptStatus.PENDING,
                to_status=status,
                reason=reject_reason,
                actor=actor,
            )
        return receipt

    def _seed_demo_win(self, demo, moderator):
        """Один гарантированный выигрыш demo — проводим розыгрыш, пока это единственный
        принятый чек в системе, чтобы именно он и победил."""
        winning_fn = _fn("1", 0)
        receipt = Receipt.objects.filter(fn=winning_fn, fd="1", fp="1").first()
        if receipt is not None and receipt.status == ReceiptStatus.WON:
            return

        if receipt is None:
            if Receipt.objects.filter(status=ReceiptStatus.ACCEPTED).exists():
                # Не первый запуск вразнобой — в системе уже есть другие принятые
                # чеки, и честно гарантировать победу именно demo нельзя. Пропускаем,
                # остальные 25 чеков demo всё равно будут созданы ниже.
                return
            receipt = self._seed_receipt(
                demo,
                fn=winning_fn,
                amount="3000.00",
                days_ago=20,
                status=ReceiptStatus.ACCEPTED,
                actor=moderator,
            )

        run_draw(title="Демо: ваш выигрыш", winners_count=1, seed="demo-win", actor=moderator)

    def _seed_demo_variety(self, demo, moderator):
        for i in range(4):
            self._seed_receipt(
                demo,
                fn=_fn("1", 10 + i),
                amount="1500.00",
                days_ago=i,
                status=ReceiptStatus.PENDING,
            )

        for i in range(13):
            self._seed_receipt(
                demo,
                fn=_fn("1", 20 + i),
                amount=str(1000 + i * 500),
                days_ago=5 + i,
                status=ReceiptStatus.ACCEPTED,
                actor=moderator,
            )

        for i in range(7):
            self._seed_receipt(
                demo,
                fn=_fn("1", 40 + i),
                amount="1200.00",
                days_ago=3 + i,
                status=ReceiptStatus.REJECTED,
                reject_reason=REJECT_REASONS[i % len(REJECT_REASONS)],
                actor=moderator,
            )

    def _seed_stranger(self, stranger, moderator):
        self._seed_receipt(
            stranger, fn=_fn("2", 0), amount="1800.00", days_ago=2, status=ReceiptStatus.PENDING
        )
        self._seed_receipt(
            stranger,
            fn=_fn("2", 1),
            amount="2200.00",
            days_ago=4,
            status=ReceiptStatus.ACCEPTED,
            actor=moderator,
        )

    def _seed_bulk_users_and_draw(self, moderator):
        for i in range(15):
            user = self._get_or_create_user(f"participant{i}", f"participant{i}")
            self._seed_receipt(
                user,
                fn=_fn("3", i),
                amount=str(1000 + i * 100),
                days_ago=i + 1,
                status=ReceiptStatus.ACCEPTED,
                actor=moderator,
            )

        if Draw.objects.filter(title=BULK_DRAW_TITLE).exists():
            return
        run_draw(title=BULK_DRAW_TITLE, winners_count=3, seed="demo-bulk-draw", actor=moderator)
