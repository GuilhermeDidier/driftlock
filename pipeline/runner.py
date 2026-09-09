"""Orchestrates one ingestion: read, judge, and only then publish.

Entry point is `run_ingestion(source)`. It is deliberately a plain callable
with no queue coupling -- swapping it onto Celery later means wrapping this
function, not rewriting it.

The control flow is the product:

    fetch -> extract -> validate
        pass/partial -> publish the clean rows
        drift        -> publish nothing, then try to heal
                        heal -> propose -> PROVE -> promote -> re-validate
                        no proof, no promotion, still nothing published
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from contracts.engine import Verdict, validate
from sources.adapters import get_adapter
from sources.models import GoldenFixture, Mapping, Source

from .healing import HealerUnavailable, Usage, normalise, propose, prove
from .models import ExtractedRecord, HealAttempt, IngestionRun, RunEvent


class Narrator:
    """Appends the run's story in order, so the UI can replay the decision."""

    def __init__(self, run: IngestionRun):
        self.run = run
        self._seq = 0

    def __call__(self, code: str, message: str, level: str = RunEvent.Level.INFO, **data):
        self._seq += 1
        RunEvent.objects.create(
            run=self.run, seq=self._seq, code=code, message=message,
            level=level, data=data,
        )


def _store_records(run: IngestionRun, report, published: bool) -> None:
    """Persist every row with the status the verdict assigns it.

    Withheld rows are kept, not dropped. When a batch fails closed the rows it
    would have published are the evidence for whether the block was right.
    """
    rows = []
    for record in report.records:
        if not published:
            status = ExtractedRecord.Status.WITHHELD
        elif record.ok:
            status = ExtractedRecord.Status.PUBLISHED
        else:
            status = ExtractedRecord.Status.QUARANTINED
        rows.append(ExtractedRecord(
            run=run, index=record.index, status=status,
            raw=record.raw,
            value={k: (v.isoformat() if hasattr(v, "isoformat") else v)
                   for k, v in record.value.items()},
            violations=[
                {"code": v.code, "field": v.field, "message": v.message,
                 "observed": v.observed, "expected": v.expected}
                for v in record.violations
            ],
        ))
    ExtractedRecord.objects.bulk_create(rows)


def _capture_baseline(source: Source, report) -> None:
    """Remember what a clean run looked like, so the next heal has a bar to clear.

    Only one automatic capture is kept -- the newest. Pinned fixtures are never
    touched here; those belong to whoever pinned them.
    """
    records = [
        {k: normalise(v) for k, v in record.value.items()} for record in report.clean
    ]
    if not records:
        return
    source.fixtures.filter(pinned=False).delete()
    GoldenFixture.objects.create(
        source=source, pinned=False, records=records,
        name=f"clean run {timezone.now():%Y-%m-%d %H:%M}",
    )


def _finish(run: IngestionRun, report, status: str, published: bool) -> IngestionRun:
    _store_records(run, report, published)
    run.status = status
    run.verdict = report.verdict.value
    run.records_read = len(report.records)
    run.records_published = len(report.clean) if published else 0
    run.records_quarantined = len(report.quarantined) if published else 0
    run.drift_detected = report.verdict is Verdict.DRIFT
    run.report = report.summary()
    run.finished_at = timezone.now()
    run.save()
    if published:
        _capture_baseline(run.source, report)
    return run


@transaction.atomic
def _promote(source: Source, candidate: Mapping, current: Mapping | None) -> None:
    if current:
        current.status = Mapping.Status.RETIRED
        current.save(update_fields=["status"])
    candidate.status = Mapping.Status.ACTIVE
    candidate.promoted_at = timezone.now()
    candidate.save(update_fields=["status", "promoted_at"])


def run_ingestion(
    source: Source, allow_heal: bool = True, heal_blocked_reason: str = ""
) -> IngestionRun:
    run = IngestionRun.objects.create(source=source)
    say = Narrator(run)
    adapter = get_adapter(source.kind)
    contract = source.contract.to_spec()

    mapping = source.active_mapping
    if mapping is None:
        run.status = IngestionRun.Status.ERROR
        run.error = "source has no active mapping"
        run.finished_at = timezone.now()
        run.save()
        say("no_mapping", "Source has no active mapping.", RunEvent.Level.BLOCK)
        return run

    run.mapping = mapping
    run.save(update_fields=["mapping"])

    try:
        say("fetch", f"Reading {source.kind} source {source.key}.")
        raw = adapter.fetch(source.config)

        say("extract", f"Extracting with mapping v{mapping.version}.",
            mapping_version=mapping.version)
        rows = adapter.extract(raw, mapping.rules, source.config)

        report = validate(contract, rows)
        say("validate", f"Validated {len(rows)} records: verdict {report.verdict.value}.",
            **report.summary())

    except Exception as exc:
        run.status = IngestionRun.Status.ERROR
        run.error = f"{type(exc).__name__}: {exc}"
        run.finished_at = timezone.now()
        run.save()
        say("error", run.error, RunEvent.Level.BLOCK)
        return run

    if report.verdict is not Verdict.DRIFT:
        say("publish",
            f"Published {len(report.clean)} records, quarantined {len(report.quarantined)}.",
            RunEvent.Level.OK)
        return _finish(run, report, IngestionRun.Status.PUBLISHED, published=True)

    # --- drift: nothing ships until something is proven ---------------------
    broken = [v.message for v in report.batch_violations]
    say("drift_detected",
        "Source no longer matches its contract. Publishing nothing.",
        RunEvent.Level.BLOCK, violations=broken)

    if not allow_heal:
        # Say why out loud. A pipeline that goes quiet is the thing this whole
        # project exists to prevent, and that applies to its own limits too.
        say("heal_skipped",
            heal_blocked_reason or "Repairs are turned off for this run.",
            RunEvent.Level.WARN)
        return _finish(run, report, IngestionRun.Status.BLOCKED, published=False)

    healed_report = _attempt_heal(run, say, source, contract, mapping, raw, report)
    if healed_report is None:
        say("blocked",
            "No candidate mapping passed the proof gate. Failing closed.",
            RunEvent.Level.BLOCK)
        return _finish(run, report, IngestionRun.Status.BLOCKED, published=False)

    say("publish",
        f"Published {len(healed_report.clean)} records after healing.",
        RunEvent.Level.OK)
    return _finish(run, healed_report, IngestionRun.Status.HEALED, published=True)


def _attempt_heal(run, say, source, contract, current: Mapping, raw: str, report):
    """Try to repair the mapping. Returns a clean report, or None.

    Two independent gates must both open before a candidate is promoted:

      1. Contract gate -- re-reading today's payload with the candidate clears
         the drift. Proof it fixes what actually broke.
      2. Continuity gate -- the candidate recovers the records we already
         trust, matched by key, compared on the fields declared stable. Proof
         it found the same facts rather than something merely well-formed.

    Gate one alone accepts a mapping that produces a tidy batch of the wrong
    values. Gate two alone accepts a mapping that agrees with history while
    still being broken today. Neither is sufficient by itself.
    """
    conf = settings.DRIFTLOCK
    max_attempts = conf["HEAL_MAX_ATTEMPTS"]
    budget = Decimal(str(conf["HEAL_MAX_USD_PER_RUN"]))
    spent = Decimal("0")
    last_cost = Decimal("0")
    adapter = get_adapter(source.kind)
    failure = "\n".join(v.message for v in report.batch_violations)

    # If no row survived, the row selector itself is suspect and the whole
    # mapping is up for replacement. Otherwise only the flagged fields are.
    rows_gone = not report.records or any(
        v.code == "too_few_records" for v in report.batch_violations
    )
    targets = None if rows_gone else {v.field for v in report.batch_violations if v.field}

    for attempt in range(1, max_attempts + 1):
        # Stop when the *next* attempt would not fit, not merely once the
        # budget is already blown -- a backward-looking check always overspends
        # by one attempt.
        if spent + last_cost > budget:
            say("budget_exhausted",
                f"Heal budget of ${budget} would be exceeded by another attempt.",
                RunEvent.Level.WARN, spent_usd=str(spent))
            break

        say("heal_start", f"Heal attempt {attempt} of {max_attempts}.", attempt=attempt)

        try:
            digest = adapter.structure_digest(raw, conf["HEAL_DOM_CHAR_BUDGET"])
            proposal = propose(
                source, contract, current.rules, digest, failure, targets=targets
            )
        except HealerUnavailable as exc:
            HealAttempt.objects.create(
                run=run, source=source, attempt=attempt, from_mapping=current,
                outcome=HealAttempt.Outcome.FAILED, reason=str(exc),
            )
            say("heal_unavailable", str(exc), RunEvent.Level.WARN)
            break
        except Exception as exc:
            HealAttempt.objects.create(
                run=run, source=source, attempt=attempt, from_mapping=current,
                outcome=HealAttempt.Outcome.FAILED,
                reason=f"{type(exc).__name__}: {exc}",
            )
            say("heal_error", f"Healer failed: {exc}", RunEvent.Level.WARN)
            continue

        usage: Usage = proposal.usage
        last_cost = usage.cost_usd
        spent += last_cost
        run.cost_usd = spent
        run.save(update_fields=["cost_usd"])

        next_version = source.mappings.order_by("-version").first().version + 1
        candidate = Mapping.objects.create(
            source=source, version=next_version,
            status=Mapping.Status.CANDIDATE, origin=Mapping.Origin.HEAL,
            rules=proposal.rules, parent=current, note=proposal.notes,
        )
        say("candidate_proposed",
            f"Candidate v{candidate.version} proposed. {proposal.notes}",
            diff=candidate.diff_against(current), cost_usd=str(usage.cost_usd))

        heal = HealAttempt(
            run=run, source=source, attempt=attempt, from_mapping=current,
            candidate=candidate, model=usage.model,
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd, latency_ms=usage.latency_ms,
        )

        def refuse(reason: str, message: str) -> None:
            candidate.status = Mapping.Status.REJECTED
            candidate.save(update_fields=["status"])
            heal.outcome = HealAttempt.Outcome.REJECTED
            heal.reason = reason
            heal.save()
            say("candidate_rejected", message, RunEvent.Level.BLOCK)

        # Gate one.
        try:
            retry_rows = adapter.extract(raw, proposal.rules, source.config)
        except Exception as exc:
            refuse(f"candidate could not be run: {exc}",
                   f"Candidate v{candidate.version} does not even run: {exc}.")
            continue

        retry_report = validate(contract, retry_rows)
        if retry_report.verdict is Verdict.DRIFT:
            refuse("still drifts on the current payload",
                   f"Candidate v{candidate.version} still fails the contract on "
                   "today's payload.")
            continue
        say("gate_contract", "Gate 1 passed: the candidate clears the contract.",
            RunEvent.Level.OK, verdict=retry_report.verdict.value)

        # Gate two.
        produced = [r.value for r in retry_report.clean]
        continuity, origin = prove(source, contract, produced)
        heal.fixtures_total = continuity.baseline_size
        heal.fixtures_passed = continuity.matched
        heal.fixture_results = continuity.mismatches[:20]

        say("gate_continuity", f"Gate 2 against {origin}: {continuity.summary}.",
            RunEvent.Level.OK if continuity.passed else RunEvent.Level.WARN,
            baseline_size=continuity.baseline_size, matched=continuity.matched,
            rate=round(continuity.rate, 4), threshold=continuity.threshold)

        if not continuity.passed:
            refuse(f"continuity gate refused the candidate: {continuity.summary}",
                   f"Candidate v{candidate.version} refused: {continuity.summary}.")
            continue

        _promote(source, candidate, current)
        heal.outcome = HealAttempt.Outcome.PROMOTED
        heal.reason = f"contract cleared; {continuity.summary}"
        heal.save()

        run.mapping = candidate
        run.save(update_fields=["mapping"])
        say("promoted",
            f"Candidate v{candidate.version} promoted. Both gates passed.",
            RunEvent.Level.OK, version=candidate.version,
            diff=candidate.diff_against(current))
        return retry_report

    return None
