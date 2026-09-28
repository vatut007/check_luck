import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from config.promo import PromoConfig
from receipts.validators import (
    FUTURE_TOLERANCE,
    ValidationError,
    validate_amount,
    validate_fd,
    validate_fn,
    validate_fp,
    validate_purchase_datetime,
)

MOSCOW = ZoneInfo("Europe/Moscow")
FIXED_NOW = dt.datetime(2026, 11, 5, tzinfo=dt.UTC)


@pytest.fixture
def promo():
    return PromoConfig(
        start_date=dt.date(2026, 10, 1),
        end_date=dt.date(2026, 10, 31),
        timezone=MOSCOW,
        min_amount=Decimal("1000"),
        photo_max_mb=5,
    )


class TestValidateFn:
    def test_valid_trims_whitespace(self):
        assert validate_fn(" 1234567890123456 ") == "1234567890123456"

    @pytest.mark.parametrize("value", ["123", "12345678901234567", "abcd567890123456", ""])
    def test_invalid(self, value):
        with pytest.raises(ValidationError):
            validate_fn(value)


@pytest.mark.parametrize("func", [validate_fd, validate_fp])
class TestValidateFdFp:
    def test_valid_trims_whitespace(self, func):
        assert func(" 123 ") == "123"

    @pytest.mark.parametrize("value", ["", "12345678901", "12a"])
    def test_invalid(self, func, value):
        with pytest.raises(ValidationError):
            func(value)


class TestValidateAmount:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("1000.00", Decimal("1000.00")),
            ("1000,00", Decimal("1000.00")),
            (" 1500 ", Decimal("1500")),
            (Decimal("2000.50"), Decimal("2000.50")),
        ],
    )
    def test_valid(self, value, expected):
        assert validate_amount(value, Decimal("1000")) == expected

    def test_at_minimum_is_valid(self):
        assert validate_amount("1000.00", Decimal("1000")) == Decimal("1000.00")

    def test_below_minimum_is_invalid(self):
        with pytest.raises(ValidationError):
            validate_amount("999.99", Decimal("1000"))

    def test_too_many_decimals_is_invalid(self):
        with pytest.raises(ValidationError):
            validate_amount("1000.001", Decimal("1000"))

    @pytest.mark.parametrize("value", ["0", "-5", "not-a-number", ""])
    def test_invalid(self, value):
        with pytest.raises(ValidationError):
            validate_amount(value, Decimal("1000"))


class TestValidatePurchaseDatetime:
    def test_first_day_midnight_is_valid(self, promo):
        value = dt.datetime(2026, 10, 1, 0, 0, tzinfo=MOSCOW)
        assert validate_purchase_datetime(value, promo, now=FIXED_NOW) == value

    def test_last_day_end_of_day_is_valid(self, promo):
        value = dt.datetime(2026, 10, 31, 23, 59, tzinfo=MOSCOW)
        assert validate_purchase_datetime(value, promo, now=FIXED_NOW) == value

    def test_day_before_period_is_invalid(self, promo):
        value = dt.datetime(2026, 9, 30, 23, 59, tzinfo=MOSCOW)
        with pytest.raises(ValidationError):
            validate_purchase_datetime(value, promo, now=FIXED_NOW)

    def test_day_after_period_is_invalid(self, promo):
        value = dt.datetime(2026, 11, 1, 0, 0, tzinfo=MOSCOW)
        with pytest.raises(ValidationError):
            validate_purchase_datetime(value, promo, now=FIXED_NOW)

    def test_naive_value_is_tagged_with_promo_timezone(self, promo):
        value = dt.datetime(2026, 10, 15, 12, 0)
        result = validate_purchase_datetime(value, promo, now=FIXED_NOW)
        assert result.tzinfo is not None
        assert result.astimezone(MOSCOW).date() == dt.date(2026, 10, 15)

    def test_within_future_tolerance_is_valid(self, promo):
        now = dt.datetime(2026, 10, 15, 10, 0, tzinfo=dt.UTC)
        value = (now + FUTURE_TOLERANCE).astimezone(MOSCOW)
        assert validate_purchase_datetime(value, promo, now=now) == value

    def test_beyond_future_tolerance_is_invalid(self, promo):
        now = dt.datetime(2026, 10, 15, 10, 0, tzinfo=dt.UTC)
        value = (now + FUTURE_TOLERANCE + dt.timedelta(minutes=1)).astimezone(MOSCOW)
        with pytest.raises(ValidationError):
            validate_purchase_datetime(value, promo, now=now)

    def test_vladivostok_late_evening_last_day_counts(self, promo):
        # 31 октября 23:30 по Владивостоку (UTC+10) — в Москве ещё 16:30 того же дня.
        vladivostok = ZoneInfo("Asia/Vladivostok")
        value = dt.datetime(2026, 10, 31, 23, 30, tzinfo=vladivostok)
        assert validate_purchase_datetime(value, promo, now=FIXED_NOW) == value
