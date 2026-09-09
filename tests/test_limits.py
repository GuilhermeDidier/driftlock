"""Limits on the public demo.

The repair button spends real money on a real account and is exposed to anyone
with the URL. These tests cover the two things that keeps honest: a global
ceiling, and a per-client rate.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from api.limits import heal_budget, spend_last_24h
from api.throttling import RunThrottle
from pipeline import runner
from pipeline.healing import Proposal, Usage
from pipeline.models import HealAttempt, IngestionRun
from sources.models import Mapping

from .factories import HEALED_RULES, RENAMED_CSV


def stub_healer(monkeypatch, rules=HEALED_RULES):
    def fake_propose(*args, **kwargs):
        return Proposal(
            rules=rules, notes="stubbed",
            usage=Usage(model="claude-opus-5", input_tokens=1000, output_tokens=200),
        )
    monkeypatch.setattr(runner, "propose", fake_propose)


def break_source(source):
    source.config = {"inline": RENAMED_CSV}
    source.save()


class TestSpendAccounting:
    def test_spend_is_summed_from_runs_not_a_counter(self, source):
        IngestionRun.objects.create(source=source, cost_usd=Decimal("0.02"))
        IngestionRun.objects.create(source=source, cost_usd=Decimal("0.03"))
        assert spend_last_24h() == Decimal("0.05")

    def test_runs_outside_the_window_do_not_count(self, source):
        old = IngestionRun.objects.create(source=source, cost_usd=Decimal("5.00"))
        IngestionRun.objects.filter(pk=old.pk).update(
            started_at=timezone.now() - timezone.timedelta(hours=25)
        )
        assert spend_last_24h() == Decimal("0")

    def test_budget_reports_what_is_left(self, source, settings):
        settings.DRIFTLOCK = {**settings.DRIFTLOCK, "PUBLIC_DAILY_USD_CAP": 1.0}
        IngestionRun.objects.create(source=source, cost_usd=Decimal("0.25"))
        budget = heal_budget()
        assert budget.remaining == Decimal("0.75")
        assert budget.exhausted is False

    def test_budget_is_exhausted_at_the_cap_not_past_it(self, source, settings):
        settings.DRIFTLOCK = {**settings.DRIFTLOCK, "PUBLIC_DAILY_USD_CAP": 0.10}
        IngestionRun.objects.create(source=source, cost_usd=Decimal("0.10"))
        assert heal_budget().exhausted is True


class TestBudgetGovernsRepairs:
    def test_a_run_under_budget_repairs(self, source, client, monkeypatch, settings):
        settings.DRIFTLOCK = {**settings.DRIFTLOCK, "PUBLIC_DAILY_USD_CAP": 1.0}
        runner.run_ingestion(source)          # clean run establishes the baseline
        break_source(source)
        stub_healer(monkeypatch)

        response = client.post(f"/api/sources/{source.key}/run/",
                               content_type="application/json", data={})

        assert response.status_code == 201
        assert response.json()["status"] == IngestionRun.Status.HEALED
        assert response.json()["budget"]["exhausted"] is False

    def test_past_the_cap_drift_is_still_caught_and_still_fails_closed(
        self, source, client, monkeypatch, settings
    ):
        """The demo degrades to detection, it does not degrade to silence."""
        settings.DRIFTLOCK = {**settings.DRIFTLOCK, "PUBLIC_DAILY_USD_CAP": 0.001}
        runner.run_ingestion(source)
        break_source(source)
        stub_healer(monkeypatch)
        IngestionRun.objects.filter(pk=IngestionRun.objects.first().pk).update(
            cost_usd=Decimal("0.50")
        )

        body = client.post(f"/api/sources/{source.key}/run/",
                           content_type="application/json", data={}).json()

        assert body["status"] == IngestionRun.Status.BLOCKED
        assert body["drift_detected"] is True          # still detected
        assert body["records_published"] == 0          # still fails closed
        assert body["budget"]["exhausted"] is True
        assert HealAttempt.objects.count() == 0        # but nothing was paid for

    def test_the_withheld_repair_is_narrated(self, source, client, monkeypatch, settings):
        settings.DRIFTLOCK = {**settings.DRIFTLOCK, "PUBLIC_DAILY_USD_CAP": 0.001}
        runner.run_ingestion(source)
        break_source(source)
        stub_healer(monkeypatch)
        IngestionRun.objects.filter(pk=IngestionRun.objects.first().pk).update(
            cost_usd=Decimal("0.50")
        )

        body = client.post(f"/api/sources/{source.key}/run/",
                           content_type="application/json", data={}).json()

        skipped = [e for e in body["events"] if e["code"] == "heal_skipped"]
        assert len(skipped) == 1
        assert "budget" in skipped[0]["message"]
        source.refresh_from_db()
        assert source.active_mapping.version == 1      # nothing was promoted

    def test_the_cap_cannot_be_overridden_by_the_request(
        self, source, client, monkeypatch, settings
    ):
        """The old endpoint took allow_heal from the caller. It must not."""
        settings.DRIFTLOCK = {**settings.DRIFTLOCK, "PUBLIC_DAILY_USD_CAP": 0.001}
        runner.run_ingestion(source)
        break_source(source)
        stub_healer(monkeypatch)
        IngestionRun.objects.filter(pk=IngestionRun.objects.first().pk).update(
            cost_usd=Decimal("0.50")
        )

        body = client.post(f"/api/sources/{source.key}/run/",
                           content_type="application/json",
                           data={"allow_heal": True}).json()

        assert body["status"] == IngestionRun.Status.BLOCKED
        assert HealAttempt.objects.count() == 0


class TestRateLimit:
    """DRF binds THROTTLE_RATES on the class at import time, so the rate is
    patched where it actually lives rather than through override_settings."""

    @staticmethod
    def set_rate(monkeypatch, rate: str):
        monkeypatch.setattr(
            RunThrottle, "THROTTLE_RATES", {"run": rate, "layout": "60/hour"},
        )

    def test_one_client_cannot_drain_the_day(self, source, client, monkeypatch):
        self.set_rate(monkeypatch, "2/hour")
        url = f"/api/sources/{source.key}/run/"

        codes = [
            client.post(url, content_type="application/json", data={}).status_code
            for _ in range(3)
        ]

        assert codes == [201, 201, 429]

    def test_reading_state_is_never_throttled(self, source, client, monkeypatch):
        self.set_rate(monkeypatch, "1/hour")
        url = f"/api/sources/{source.key}/run/"
        client.post(url, content_type="application/json", data={})
        assert client.post(url, content_type="application/json", data={}).status_code == 429

        for _ in range(5):
            assert client.get("/api/state/").status_code == 200


class TestStateExposesTheBudget:
    def test_state_reports_remaining_budget(self, source, client, settings):
        settings.DRIFTLOCK = {**settings.DRIFTLOCK, "PUBLIC_DAILY_USD_CAP": 1.0}
        IngestionRun.objects.create(source=source, cost_usd=Decimal("0.40"))

        budget = client.get("/api/state/").json()["budget"]

        assert budget["cap_usd"] == "1.0"
        assert Decimal(budget["remaining_usd"]) == Decimal("0.60")
        assert budget["exhausted"] is False


class TestHealScope:
    """A working rule must be unreachable from a repair, not merely discouraged."""

    @staticmethod
    def html_source(db_source):
        from sources.models import Mapping, Source

        db_source.kind = Source.Kind.HTML
        db_source.config = {"url": "http://example.test/"}
        db_source.save()
        mapping = db_source.mappings.get(version=1)
        mapping.rules = {
            "__row__": {"selector": ".card"},
            "sku": {"selector": ".sku", "attr": "text"},
            "name": {"selector": ".title", "attr": "text"},
            "price": {"selector": ".price", "attr": "text"},
        }
        mapping.save()
        return db_source, mapping

    @staticmethod
    def fake_client(monkeypatch):
        """A model that helpfully rewrites everything, including what works."""
        from types import SimpleNamespace

        from pipeline import healing

        parsed = SimpleNamespace(
            row_selector=".brand-new-row",
            notes="rewrote the lot",
            fields=[
                SimpleNamespace(field="price", selector=".amount", attr="text"),
                SimpleNamespace(field="sku", selector=".code", attr="text"),
                SimpleNamespace(field="name", selector=".headline", attr="text"),
            ],
        )
        response = SimpleNamespace(
            parsed_output=parsed,
            usage=SimpleNamespace(input_tokens=100, output_tokens=40),
        )
        client = SimpleNamespace(
            messages=SimpleNamespace(parse=lambda **kwargs: response)
        )
        monkeypatch.setattr(healing, "_client", lambda: client)

    def test_only_the_flagged_field_is_replaced(self, source, monkeypatch):
        from pipeline.healing import propose

        db_source, mapping = self.html_source(source)
        self.fake_client(monkeypatch)

        proposal = propose(
            db_source, db_source.contract.to_spec(), mapping.rules,
            digest="<div class=card>…</div>", failure="price is present in 0% of records",
            targets={"price"},
        )

        assert proposal.rules["price"] == {"selector": ".amount", "attr": "text"}
        # returned by the model, and dropped, because these were not broken
        assert proposal.rules["sku"] == {"selector": ".sku", "attr": "text"}
        assert proposal.rules["name"] == {"selector": ".title", "attr": "text"}
        assert proposal.rules["__row__"] == {"selector": ".card"}

    def test_everything_is_replaceable_when_the_rows_are_gone(self, source, monkeypatch):
        from pipeline.healing import propose

        db_source, mapping = self.html_source(source)
        self.fake_client(monkeypatch)

        proposal = propose(
            db_source, db_source.contract.to_spec(), mapping.rules,
            digest="<article>…</article>", failure="batch has 0 records",
            targets=None,
        )

        assert proposal.rules["__row__"] == {"selector": ".brand-new-row"}
        assert proposal.rules["sku"] == {"selector": ".code", "attr": "text"}
