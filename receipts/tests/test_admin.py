import pytest
from django.urls import reverse

from receipts.admin import ReceiptAdminForm
from receipts.models import ReceiptStatus
from receipts.tests.factories import ReceiptFactory, UserFactory

pytestmark = pytest.mark.django_db


def _staff_user():
    return UserFactory(is_staff=True, is_superuser=True)


def _change_url(receipt):
    return reverse("admin:receipts_receipt_change", args=[receipt.pk])


def _post_change(client, receipt, **field_overrides):
    """Собирает валидный POST для change-формы админки, читая текущие значения
    и management-form инлайна прямо из GET-ответа — не гадаем префиксы формсета руками."""
    get_response = client.get(_change_url(receipt))
    data = {}
    for field in get_response.context["adminform"].form:
        value = field.value()
        data[field.html_name] = "" if value is None else value

    for inline_formset in get_response.context["inline_admin_formsets"]:
        formset = inline_formset.formset
        for name, value in formset.management_form.initial.items():
            data[f"{formset.prefix}-{name}"] = value

    data.update(field_overrides)
    return client.post(_change_url(receipt), data=data)


class TestReceiptAdminForm:
    def test_won_choice_not_available_for_pending_receipt(self):
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)
        form = ReceiptAdminForm(instance=receipt)
        values = [value for value, _ in form.fields["status"].choices]
        assert ReceiptStatus.WON not in values

    def test_status_field_disabled_for_already_won_receipt(self):
        receipt = ReceiptFactory(status=ReceiptStatus.WON)
        form = ReceiptAdminForm(instance=receipt)
        assert form.fields["status"].disabled is True


class TestReceiptChangeView:
    def test_accept_creates_log_and_redirects(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        response = _post_change(client, receipt, status=ReceiptStatus.ACCEPTED)

        receipt.refresh_from_db()
        assert response.status_code == 302
        assert receipt.status == ReceiptStatus.ACCEPTED
        log = receipt.status_logs.latest("created_at")
        assert log.to_status == ReceiptStatus.ACCEPTED
        assert log.actor == staff

    def test_reject_without_reason_does_not_save(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        response = _post_change(client, receipt, status=ReceiptStatus.REJECTED, reject_reason="")

        receipt.refresh_from_db()
        assert response.status_code == 200
        assert receipt.status == ReceiptStatus.PENDING

    def test_reject_with_reason_saves(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        response = _post_change(
            client,
            receipt,
            status=ReceiptStatus.REJECTED,
            reject_reason="Нечитаемое фото",
        )

        receipt.refresh_from_db()
        assert response.status_code == 302
        assert receipt.status == ReceiptStatus.REJECTED
        assert receipt.reject_reason == "Нечитаемое фото"

    def test_posting_won_directly_is_rejected(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        response = _post_change(client, receipt, status=ReceiptStatus.WON)

        receipt.refresh_from_db()
        assert response.status_code == 200
        assert receipt.status == ReceiptStatus.PENDING

    def test_cannot_moderate_already_moderated_receipt(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.ACCEPTED)

        response = _post_change(client, receipt, status=ReceiptStatus.REJECTED, reject_reason="x")

        receipt.refresh_from_db()
        assert response.status_code == 200
        assert receipt.status == ReceiptStatus.ACCEPTED


class TestReceiptAdminActions:
    def test_accept_selected_skips_non_pending(self, client):
        staff = _staff_user()
        client.force_login(staff)
        pending = ReceiptFactory(status=ReceiptStatus.PENDING)
        accepted = ReceiptFactory(status=ReceiptStatus.ACCEPTED)

        client.post(
            reverse("admin:receipts_receipt_changelist"),
            data={
                "action": "accept_selected",
                "_selected_action": [pending.pk, accepted.pk],
            },
        )

        pending.refresh_from_db()
        accepted.refresh_from_db()
        assert pending.status == ReceiptStatus.ACCEPTED
        assert accepted.status == ReceiptStatus.ACCEPTED

    def test_reject_selected_shows_intermediate_page(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        response = client.post(
            reverse("admin:receipts_receipt_changelist"),
            data={"action": "reject_selected", "_selected_action": [receipt.pk]},
        )

        assert response.status_code == 200
        assert b"reason" in response.content

    def test_reject_selected_apply_rejects_with_reason(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        response = client.post(
            reverse("admin:receipts_receipt_changelist"),
            data={
                "action": "reject_selected",
                "_selected_action": [receipt.pk],
                "apply": "1",
                "reason": "Нечитаемое фото",
            },
        )

        receipt.refresh_from_db()
        assert response.status_code == 302
        assert receipt.status == ReceiptStatus.REJECTED
        assert receipt.reject_reason == "Нечитаемое фото"

    def test_reject_selected_apply_without_reason_rejects_nothing(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        client.post(
            reverse("admin:receipts_receipt_changelist"),
            data={
                "action": "reject_selected",
                "_selected_action": [receipt.pk],
                "apply": "1",
                "reason": "",
            },
        )

        receipt.refresh_from_db()
        assert receipt.status == ReceiptStatus.PENDING


class TestExportAcceptedCsv:
    def test_only_accepted_receipts_are_exported(self, client):
        staff = _staff_user()
        client.force_login(staff)
        accepted = ReceiptFactory(status=ReceiptStatus.ACCEPTED)
        pending = ReceiptFactory(status=ReceiptStatus.PENDING)
        rejected = ReceiptFactory(status=ReceiptStatus.REJECTED, reject_reason="x")

        response = client.post(
            reverse("admin:receipts_receipt_changelist"),
            data={
                "action": "export_accepted_csv",
                "_selected_action": [accepted.pk, pending.pk, rejected.pk],
            },
        )

        body = b"".join(response.streaming_content).decode("utf-8-sig")
        assert accepted.fn in body
        assert pending.fn not in body
        assert rejected.fn not in body

    def test_response_starts_with_utf8_bom(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.ACCEPTED)

        response = client.post(
            reverse("admin:receipts_receipt_changelist"),
            data={"action": "export_accepted_csv", "_selected_action": [receipt.pk]},
        )

        raw = b"".join(response.streaming_content)
        assert raw.startswith(b"\xef\xbb\xbf")

    def test_uses_semicolon_delimiter(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.ACCEPTED)

        response = client.post(
            reverse("admin:receipts_receipt_changelist"),
            data={"action": "export_accepted_csv", "_selected_action": [receipt.pk]},
        )

        body = b"".join(response.streaming_content).decode("utf-8-sig")
        header_line = body.splitlines()[0]
        assert header_line.count(";") >= 7

    def test_content_type_and_filename(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.ACCEPTED)

        response = client.post(
            reverse("admin:receipts_receipt_changelist"),
            data={"action": "export_accepted_csv", "_selected_action": [receipt.pk]},
        )

        assert response["Content-Type"] == "text/csv; charset=utf-8"
        assert response["Content-Disposition"].startswith(
            'attachment; filename="receipts_accepted_'
        )


class TestReceiptStatusLogInline:
    def test_inline_is_read_only(self, client):
        staff = _staff_user()
        client.force_login(staff)
        receipt = ReceiptFactory(status=ReceiptStatus.PENDING)

        response = client.get(_change_url(receipt))

        inline_formset = response.context["inline_admin_formsets"][0]
        assert inline_formset.has_add_permission is False
        assert inline_formset.has_change_permission is False
