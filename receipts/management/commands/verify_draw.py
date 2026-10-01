from django.core.management.base import BaseCommand, CommandError

from receipts.models import Draw
from receipts.services import participants_hash, pick_winners


class Command(BaseCommand):
    help = (
        "Проверяет воспроизводимость розыгрыша: хэш сохранённого списка участников "
        "и повтор выбора победителей тем же зерном по тому же алгоритму."
    )

    def add_arguments(self, parser):
        parser.add_argument("draw_id", type=int)

    def handle(self, *args, **options):
        draw_id = options["draw_id"]
        try:
            draw = Draw.objects.get(pk=draw_id)
        except Draw.DoesNotExist as exc:
            raise CommandError(f"Розыгрыш #{draw_id} не найден.") from exc

        problems = []

        recomputed_hash = participants_hash(draw.participants)
        if recomputed_hash != draw.participants_hash:
            problems.append(
                f"Хэш списка участников не совпадает: записан {draw.participants_hash}, "
                f"пересчитан {recomputed_hash}. Список участников подменили."
            )

        recomputed_winners = set(pick_winners(draw.participants, draw.seed, draw.winners_count))
        actual_winners = set(draw.winning_receipts.values_list("id", flat=True))
        if recomputed_winners != actual_winners:
            problems.append(
                f"Победители не совпадают: записаны {sorted(actual_winners)}, "
                f"пересчитаны по тому же зерну {sorted(recomputed_winners)}."
            )

        if problems:
            for problem in problems:
                self.stderr.write(self.style.ERROR(problem))
            raise CommandError(f"Розыгрыш #{draw_id} не прошёл проверку.")

        self.stdout.write(self.style.SUCCESS(f"Розыгрыш #{draw_id} «{draw.title}»: OK"))
