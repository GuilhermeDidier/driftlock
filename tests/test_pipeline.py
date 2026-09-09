"""End-to-end pipeline behaviour, with the healer stubbed.

The healer is non-deterministic and costs money, so these tests replace it
with canned proposals. What is under test is not the model -- it is the two
gates standing between a proposal and production.
"""
from __future__ import annotations

import pytest

from pipeline import runner
from pipeline.healing import Proposal, Usage
from pipeline.models import ExtractedRecord, HealAttempt, IngestionRun
from sources.models import Mapping, Source

from .factories import (
    GOOD_RULES, HEALED_RULES, RENAMED_CSV, RENAMED_REPRICED_CSV,
)

def seed_baseline(source: Source) -> None:
    """One clean run, which is what earns a source its trusted records."""
    run = runner.run_ingestion(source)
    assert run.status == IngestionRun.Status.PUBLISHED


def break_source(source: Source, csv: str = RENAMED_CSV) -> None:
    source.config = {"inline": csv}
    source.save()


def stub_healer(monkeypatch, rules: dict):
    def fake_propose(*args, **kwargs):
        return Proposal(
            rules=rules, notes="stubbed",
            usage=Usage(model="claude-opus-5", input_tokens=1000, output_tokens=200),
        )
    monkeypatch.setattr(runner, "propose", fake_propose)


def no_api_key(monkeypatch):
    monkeypatch.setattr(runner.settings, "DRIFTLOCK",
                        {**runner.settings.DRIFTLOCK, "ANTHROPIC_API_KEY": ""})


class TestHappyPath:
    def test_clean_source_publishes(self, source):
        run = runner.run_ingestion(source)
        assert run.status == IngestionRun.Status.PUBLISHED
        assert run.verdict == "pass"
        assert run.records_published == 4
        assert run.drift_detected is False

    def test_a_clean_run_becomes_the_baseline(self, source):
        runner.run_ingestion(source)
        fixture = source.fixtures.get()
        assert fixture.pinned is False
        assert len(fixture.records) == 4
        assert fixture.records[0]["sku"] == "A1"


class TestFailClosed:
    def test_renamed_columns_block_the_batch(self, source, monkeypatch):
        seed_baseline(source)
        break_source(source)
        no_api_key(monkeypatch)

        run = runner.run_ingestion(source)

        assert run.status == IngestionRun.Status.BLOCKED
        assert run.drift_detected is True
        assert run.records_published == 0
        # rows are kept as evidence, just not published
        assert run.records.filter(status=ExtractedRecord.Status.WITHHELD).count() == 4

    def test_a_blocked_run_does_not_overwrite_the_baseline(self, source, monkeypatch):
        seed_baseline(source)
        original = source.fixtures.get().records
        break_source(source)
        no_api_key(monkeypatch)

        runner.run_ingestion(source)

        assert source.fixtures.get().records == original

    def test_the_block_is_narrated_in_order(self, source, monkeypatch):
        seed_baseline(source)
        break_source(source)
        no_api_key(monkeypatch)

        run = runner.run_ingestion(source)
        codes = [e.code for e in run.events.all()]
        assert codes[:3] == ["fetch", "extract", "validate"]
        assert "drift_detected" in codes
        assert codes[-1] == "blocked"


class TestGates:
    def test_correct_candidate_passes_both_gates_and_publishes(self, source, monkeypatch):
        seed_baseline(source)
        break_source(source)
        stub_healer(monkeypatch, HEALED_RULES)

        run = runner.run_ingestion(source)

        assert run.status == IngestionRun.Status.HEALED
        assert run.records_published == 4
        heal = HealAttempt.objects.get()
        assert heal.outcome == HealAttempt.Outcome.PROMOTED
        assert (heal.fixtures_passed, heal.fixtures_total) == (4, 4)

        source.refresh_from_db()
        assert source.active_mapping.version == 2
        assert source.active_mapping.origin == Mapping.Origin.HEAL
        assert source.mappings.get(version=1).status == Mapping.Status.RETIRED

        codes = [e.code for e in run.events.all()]
        assert codes.index("gate_contract") < codes.index("gate_continuity") < codes.index("promoted")

    def test_gate_one_refuses_a_candidate_that_reads_nothing(self, source, monkeypatch):
        """Contract gate: the proposal leaves the batch just as broken."""
        seed_baseline(source)
        break_source(source)
        stub_healer(monkeypatch, {
            "sku": {"column": "nope"}, "name": {"column": "nope"},
            "price": {"column": "nope"},
        })

        run = runner.run_ingestion(source)

        assert run.status == IngestionRun.Status.BLOCKED
        heal = HealAttempt.objects.first()
        assert heal.outcome == HealAttempt.Outcome.REJECTED
        assert "still drifts" in heal.reason
        # refused before the continuity gate was ever consulted
        assert "gate_continuity" not in [e.code for e in run.events.all()]
        source.refresh_from_db()
        assert source.active_mapping.version == 1

    def test_gate_two_refuses_a_tidy_batch_of_wrong_values(self, source, monkeypatch):
        """Continuity gate: well-formed, contract-clean, and wrong.

        `name` is filled from the price column. Every contract rule is
        satisfied -- the values are present, distinct and correctly typed -- so
        gate one waves it through. Only the trusted records reveal that the
        products are no longer named what they were named.
        """
        seed_baseline(source)
        break_source(source)
        stub_healer(monkeypatch, {
            "sku": {"column": "codigo"}, "name": {"column": "valor"},
            "price": {"column": "valor"},
        })

        run = runner.run_ingestion(source)

        events = {e.code for e in run.events.all()}
        assert "gate_contract" in events        # gate one opened
        assert run.status == IngestionRun.Status.BLOCKED
        heal = HealAttempt.objects.first()
        assert heal.outcome == HealAttempt.Outcome.REJECTED
        assert heal.fixtures_passed == 0        # nothing recovered correctly
        assert heal.fixtures_total == 4
        source.refresh_from_db()
        assert source.active_mapping.version == 1

    def test_volatile_fields_do_not_block_an_honest_heal(self, source, monkeypatch):
        """Prices moved and the layout changed in the same window.

        `price` is not declared stable, so its movement is data churn, not
        evidence against the mapping. Only `sku` and `name` are compared.
        """
        seed_baseline(source)
        break_source(source, RENAMED_REPRICED_CSV)
        stub_healer(monkeypatch, HEALED_RULES)

        run = runner.run_ingestion(source)

        assert run.status == IngestionRun.Status.HEALED
        published = run.records.filter(status=ExtractedRecord.Status.PUBLISHED)
        assert published.get(index=0).value["price"] == 249.90

    def test_nothing_trusted_means_nothing_promotable(self, source, monkeypatch):
        """A source that has never run cleanly has no bar to clear, so it fails closed."""
        break_source(source)  # broken on its very first run
        stub_healer(monkeypatch, HEALED_RULES)

        run = runner.run_ingestion(source)

        assert run.status == IngestionRun.Status.BLOCKED
        heal = HealAttempt.objects.first()
        assert heal.outcome == HealAttempt.Outcome.REJECTED
        assert heal.fixtures_total == 0

    def test_a_pinned_fixture_outranks_the_rolling_baseline(self, source, monkeypatch):
        seed_baseline(source)
        source.fixtures.create(
            name="confirmado por humano", pinned=True,
            records=[{"sku": "A1", "name": "Teclado Mecânico", "price": 199.90}],
        )
        break_source(source)
        stub_healer(monkeypatch, HEALED_RULES)

        run = runner.run_ingestion(source)

        # The pinned record says A1 is "Teclado Mecânico"; the source says
        # "Teclado". The human-confirmed answer wins and the heal is refused.
        heal = HealAttempt.objects.first()
        assert heal.fixtures_total == 1
        assert heal.fixtures_passed == 0
        assert run.status == IngestionRun.Status.BLOCKED


class TestBudget:
    def test_cost_is_recorded_per_run(self, source, monkeypatch):
        seed_baseline(source)
        break_source(source)
        stub_healer(monkeypatch, HEALED_RULES)

        run = runner.run_ingestion(source)
        # 1000 in @ $5/M + 200 out @ $25/M = $0.005 + $0.005
        assert float(run.cost_usd) == pytest.approx(0.010)

    def test_budget_stops_before_the_attempt_it_cannot_afford(self, source, monkeypatch):
        seed_baseline(source)
        break_source(source)
        monkeypatch.setattr(runner.settings, "DRIFTLOCK", {
            **runner.settings.DRIFTLOCK,
            "HEAL_MAX_ATTEMPTS": 5,
            "HEAL_MAX_USD_PER_RUN": 0.011,  # room for one attempt, not two
        })
        stub_healer(monkeypatch, {
            "sku": {"column": "nope"}, "name": {"column": "nope"},
            "price": {"column": "nope"},
        })

        run = runner.run_ingestion(source)

        assert HealAttempt.objects.count() == 1
        assert [e.code for e in run.events.all()].count("budget_exhausted") == 1
        assert run.status == IngestionRun.Status.BLOCKED
