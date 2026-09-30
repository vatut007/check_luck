import pytest

from receipts.qr import QrParseError, parse_qr_string


class TestParseQrString:
    def test_real_string(self):
        raw = "t=20261015T1830&s=1234.56&fn=9999078900004312&i=12345&fp=1234567890&n=1"
        result = parse_qr_string(raw)
        assert result == {
            "fn": "9999078900004312",
            "fd": "12345",
            "fp": "1234567890",
            "purchased_at": "2026-10-15T18:30",
            "amount": "1234.56",
        }

    def test_seconds_in_time_are_accepted(self):
        raw = "t=20261015T183045&s=1234.56&fn=9999078900004312&i=12345&fp=1234567890"
        result = parse_qr_string(raw)
        assert result["purchased_at"] == "2026-10-15T18:30"

    def test_param_order_does_not_matter(self):
        raw = "fp=1234567890&fn=9999078900004312&i=12345&s=1234.56&t=20261015T1830"
        result = parse_qr_string(raw)
        assert result["fn"] == "9999078900004312"

    def test_comma_as_decimal_separator(self):
        raw = "t=20261015T1830&s=1234,56&fn=9999078900004312&i=12345&fp=1234567890"
        result = parse_qr_string(raw)
        assert result["amount"] == "1234.56"

    def test_extra_params_are_ignored(self):
        raw = "t=20261015T1830&s=1234.56&fn=9999078900004312&i=12345&fp=1234567890&extra=whatever"
        result = parse_qr_string(raw)
        assert result["fn"] == "9999078900004312"

    def test_whitespace_around_string_is_trimmed(self):
        raw = "  \nt=20261015T1830&s=1234.56&fn=9999078900004312&i=12345&fp=1234567890\n  "
        result = parse_qr_string(raw)
        assert result["fn"] == "9999078900004312"

    def test_refund_receipt_is_rejected(self):
        raw = "t=20261015T1830&s=1234.56&fn=9999078900004312&i=12345&fp=1234567890&n=2"
        with pytest.raises(QrParseError, match="возврата"):
            parse_qr_string(raw)

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "fn=9999078900004312&i=12345&fp=1234567890",  # нет t и s
            "t=not-a-date&s=1234.56&fn=9999078900004312&i=12345&fp=1234567890",
            "t=20261015T1830&s=&fn=9999078900004312&i=12345&fp=1234567890",
        ],
    )
    def test_malformed_strings_raise(self, raw):
        with pytest.raises(QrParseError):
            parse_qr_string(raw)
