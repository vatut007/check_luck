"""Бизнес-логика: регистрация чека, повторная подача, модерация.

Views и serializers сюда только обращаются — сами решений не принимают.
Входные значения (fn/fd/fp/amount/purchased_at) здесь уже очищены
validators.py на уровне API; сервисы отвечают за состояние чека.
"""

import hashlib
import json
import random
import secrets

from django.db import IntegrityError, transaction

from receipts.errors import DomainError
from receipts.models import Draw, Receipt, ReceiptStatus, ReceiptStatusLog
from receipts.photos import process_photo


class DuplicateReceiptError(DomainError):
    """Чек с таким ФН+ФД+ФП уже зарегистрирован — см. docs/decisions/002."""


class InvalidTransitionError(DomainError):
    """Запрошенный переход статуса чека недопустим."""


def register_receipt(
    *, user, fn: str, fd: str, fp: str, purchased_at, amount, photo=None
) -> tuple[Receipt, bool]:
    """Регистрирует чек или повторно подаёт отклонённый. Статус всегда становится pending.

    Возвращает (receipt, created): created=False — это повторная подача
    (HTTP 200), True — новый чек (HTTP 201).

    Вызывающая сторона отвечает за photos.validate_photo() до вызова этой функции;
    саму обработку (снятие EXIF, миниатюра) делает она сама — это не поле формы,
    а производный артефакт, который в любом случае сохраняет только сервис.
    """
    photo_thumb = None
    if photo is not None:
        photo, photo_thumb = process_photo(photo)

    with transaction.atomic():
        existing = Receipt.objects.select_for_update().filter(fn=fn, fd=fd, fp=fp).first()
        if existing is not None:
            return _resubmit_or_reject(
                existing,
                user=user,
                purchased_at=purchased_at,
                amount=amount,
                photo=photo,
                photo_thumb=photo_thumb,
            )

        try:
            with transaction.atomic():
                receipt = Receipt.objects.create(
                    fn=fn,
                    fd=fd,
                    fp=fp,
                    purchased_at=purchased_at,
                    amount=amount,
                    photo=photo,
                    photo_thumb=photo_thumb,
                    user=user,
                    status=ReceiptStatus.PENDING,
                )
        except IntegrityError:
            # Гонка: кто-то успел вставить такой же чек между select и insert.
            existing = Receipt.objects.select_for_update().get(fn=fn, fd=fd, fp=fp)
            return _resubmit_or_reject(
                existing,
                user=user,
                purchased_at=purchased_at,
                amount=amount,
                photo=photo,
                photo_thumb=photo_thumb,
            )

        ReceiptStatusLog.objects.create(
            receipt=receipt, from_status="", to_status=ReceiptStatus.PENDING, actor=user
        )
        return receipt, True


def _resubmit_or_reject(
    existing: Receipt, *, user, purchased_at, amount, photo, photo_thumb
) -> tuple[Receipt, bool]:
    if existing.user_id != user.id:
        raise DuplicateReceiptError("Этот чек уже зарегистрирован другим участником.")

    if existing.status != ReceiptStatus.REJECTED:
        raise DuplicateReceiptError(
            f"Вы уже зарегистрировали этот чек, он «{existing.get_status_display()}»."
        )

    from_status = existing.status
    existing.purchased_at = purchased_at
    existing.amount = amount
    if photo is not None:
        existing.photo = photo
        existing.photo_thumb = photo_thumb
    existing.status = ReceiptStatus.PENDING
    existing.reject_reason = ""
    existing.save(
        update_fields=[
            "purchased_at",
            "amount",
            "photo",
            "photo_thumb",
            "status",
            "reject_reason",
            "updated_at",
        ]
    )
    ReceiptStatusLog.objects.create(
        receipt=existing, from_status=from_status, to_status=ReceiptStatus.PENDING, actor=user
    )
    return existing, False


def moderate_receipt(*, receipt: Receipt, actor, new_status: str, reason: str = "") -> Receipt:
    """Переводит чек pending -> accepted/rejected. Другие переходы недопустимы."""
    reason = reason.strip()

    if new_status not in (ReceiptStatus.ACCEPTED, ReceiptStatus.REJECTED):
        raise InvalidTransitionError(
            "Модерация допускает только переход в «принят» или «отклонён»."
        )
    if receipt.status != ReceiptStatus.PENDING:
        raise InvalidTransitionError(
            f"Чек в статусе «{receipt.get_status_display()}» нельзя промодерировать повторно."
        )
    if new_status == ReceiptStatus.REJECTED and not reason:
        raise InvalidTransitionError("Для отказа нужно указать причину.")

    with transaction.atomic():
        from_status = receipt.status
        receipt.status = new_status
        receipt.reject_reason = reason if new_status == ReceiptStatus.REJECTED else ""
        receipt.save(update_fields=["status", "reject_reason", "updated_at"])
        ReceiptStatusLog.objects.create(
            receipt=receipt,
            from_status=from_status,
            to_status=new_status,
            reason=reason,
            actor=actor,
        )
    return receipt


class DrawError(DomainError):
    """Розыгрыш нельзя провести с переданными параметрами."""


def pick_winners(participants: list[list[int]], seed: str, count: int) -> list[int]:
    """Детерминированный выбор победителей — один шанс на чек, один выигрыш на пользователя.

    participants — список [receipt_id, user_id], отсортированный по receipt_id (порядок
    должен быть детерминированным ещё до перемешивания). Та же пара (participants, seed)
    всегда даёт тот же результат — это и проверяет management-команда verify_draw.
    """
    user_by_receipt = {receipt_id: user_id for receipt_id, user_id in participants}
    shuffled = list(user_by_receipt.keys())
    random.Random(seed).shuffle(shuffled)

    winners: list[int] = []
    winning_users: set[int] = set()
    for receipt_id in shuffled:
        if len(winners) >= count:
            break
        user_id = user_by_receipt[receipt_id]
        if user_id in winning_users:
            continue
        winners.append(receipt_id)
        winning_users.add(user_id)

    return winners


def participants_hash(participants: list[list[int]]) -> str:
    raw = json.dumps(participants, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def run_draw(*, title: str, winners_count: int, seed: str = "", actor) -> Draw:
    """Проводит розыгрыш среди принятых чеков. Блокирует их на время розыгрыша
    (select_for_update), чтобы модератор не мог что-то принять/отклонить посреди."""
    title = title.strip()
    if not title:
        raise DrawError("Укажите название приза.")
    if winners_count < 1:
        raise DrawError("Число победителей должно быть не меньше 1.")

    seed = seed.strip() or secrets.token_hex(16)

    with transaction.atomic():
        eligible = list(
            Receipt.objects.select_for_update()
            .filter(status=ReceiptStatus.ACCEPTED)
            .order_by("id")
            .values_list("id", "user_id")
        )
        # Выиграть может только один раз на пользователя — считаем именно
        # разных участников, а не число чеков, иначе запрошенное количество
        # победителей может оказаться физически недостижимым.
        eligible_users = {user_id for _, user_id in eligible}
        if len(eligible_users) < winners_count:
            raise DrawError(
                f"Недостаточно участников (разных пользователей) для розыгрыша: "
                f"{len(eligible_users)} из {winners_count} нужных."
            )

        participants = [[receipt_id, user_id] for receipt_id, user_id in eligible]
        winner_ids = pick_winners(participants, seed, winners_count)

        draw = Draw.objects.create(
            title=title,
            winners_count=winners_count,
            seed=seed,
            participants_count=len(participants),
            participants=participants,
            participants_hash=participants_hash(participants),
            performed_by=actor,
        )

        for receipt in Receipt.objects.filter(id__in=winner_ids):
            from_status = receipt.status
            receipt.status = ReceiptStatus.WON
            receipt.prize = draw
            receipt.save(update_fields=["status", "prize", "updated_at"])
            ReceiptStatusLog.objects.create(
                receipt=receipt,
                from_status=from_status,
                to_status=ReceiptStatus.WON,
                actor=actor,
            )

    return draw
