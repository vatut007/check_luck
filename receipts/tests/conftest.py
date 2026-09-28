import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from config.promo import PromoConfig


@pytest.fixture
def promo_period(settings):
    """.env.example задаёт период в будущем (октябрь 2026) — для тестов создания
    подменяем settings.PROMO на период вокруг сегодняшнего дня."""
    today = timezone.localdate()
    promo = PromoConfig(
        start_date=today - dt.timedelta(days=5),
        end_date=today + dt.timedelta(days=5),
        timezone=ZoneInfo(settings.PROMO_TIMEZONE),
        min_amount=Decimal("1000"),
        photo_max_mb=5,
    )
    settings.PROMO = promo
    return promo
