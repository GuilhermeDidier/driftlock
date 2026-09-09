"""Spend limits for the public demo.

The repair button costs real money on a real account and is exposed to anyone
with the URL, so the demo needs a ceiling it cannot be argued past.

The spend figure is derived, never counted. Every run already records what it
cost, so the budget is a sum over those rows rather than a separate counter --
one fewer thing that can drift away from the truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class HealBudget:
    spent: Decimal
    cap: Decimal

    @property
    def remaining(self) -> Decimal:
        return max(Decimal("0"), self.cap - self.spent)

    @property
    def exhausted(self) -> bool:
        return self.spent >= self.cap

    @property
    def reason(self) -> str:
        return (
            f"the demo's 24-hour repair budget of ${self.cap} is spent; "
            "drift is still detected and the batch still fails closed"
        )

    def as_json(self) -> dict:
        return {
            "spent_usd": str(self.spent.quantize(Decimal("0.000001"))),
            "cap_usd": str(self.cap),
            "remaining_usd": str(self.remaining.quantize(Decimal("0.000001"))),
            "exhausted": self.exhausted,
        }


def spend_last_24h() -> Decimal:
    from pipeline.models import IngestionRun

    total = IngestionRun.objects.filter(
        started_at__gte=timezone.now() - WINDOW
    ).aggregate(total=Sum("cost_usd"))["total"]
    return Decimal(total or 0)


def heal_budget() -> HealBudget:
    cap = Decimal(str(settings.DRIFTLOCK["PUBLIC_DAILY_USD_CAP"]))
    return HealBudget(spent=spend_last_24h(), cap=cap)
