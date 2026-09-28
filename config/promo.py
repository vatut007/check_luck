from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class PromoConfig:
    """Правила акции, единым объектом — вместо чтения settings.* по всему коду."""

    start_date: dt.date
    end_date: dt.date
    timezone: ZoneInfo
    min_amount: Decimal
    photo_max_mb: int

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("PROMO_START must be on or before PROMO_END")

    @property
    def tz_name(self) -> str:
        return self.timezone.key
