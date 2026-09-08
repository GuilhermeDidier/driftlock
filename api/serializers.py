"""Hand-written projections.

The dashboard needs a few specific shapes, not a generic reflection of the
models, so these are plain functions rather than DRF serializers.
"""
from __future__ import annotations

from pipeline.models import ExtractedRecord, HealAttempt, IngestionRun, RunEvent
from sources.models import Mapping, Source


def contract_json(contract) -> dict:
    return {
        "key": contract.key,
        "name": contract.name,
        "min_records": contract.min_records,
        "unique_by": contract.unique_by,
        "continuity_threshold": contract.continuity_threshold,
        "fields": [
            {
                "name": f.name, "type": f.type, "description": f.description,
                "required": f.required, "stable": f.stable,
                "min_fill_rate": f.min_fill_rate,
                "min_distinct_ratio": f.min_distinct_ratio,
                "min_value": f.min_value, "max_value": f.max_value,
            }
            for f in contract.fields.all()
        ],
    }


def mapping_json(mapping: Mapping, parent: Mapping | None = None) -> dict:
    return {
        "id": mapping.id,
        "version": mapping.version,
        "status": mapping.status,
        "origin": mapping.origin,
        "rules": mapping.rules,
        "note": mapping.note,
        "created_at": mapping.created_at,
        "promoted_at": mapping.promoted_at,
        "diff": mapping.diff_against(parent if parent is not None else mapping.parent),
    }


def event_json(event: RunEvent) -> dict:
    return {
        "seq": event.seq, "at": event.at, "level": event.level,
        "code": event.code, "message": event.message, "data": event.data,
    }


def record_json(record: ExtractedRecord) -> dict:
    return {
        "index": record.index, "status": record.status,
        "value": record.value, "violations": record.violations,
    }


def heal_json(heal: HealAttempt) -> dict:
    return {
        "attempt": heal.attempt,
        "outcome": heal.outcome,
        "reason": heal.reason,
        "from_version": heal.from_mapping.version if heal.from_mapping else None,
        "candidate_version": heal.candidate.version if heal.candidate else None,
        "candidate_rules": heal.candidate.rules if heal.candidate else None,
        "baseline_size": heal.fixtures_total,
        "recovered": heal.fixtures_passed,
        "mismatches": heal.fixture_results,
        "model": heal.model,
        "input_tokens": heal.input_tokens,
        "output_tokens": heal.output_tokens,
        "cost_usd": str(heal.cost_usd),
        "latency_ms": heal.latency_ms,
    }


def run_summary(run: IngestionRun) -> dict:
    return {
        "id": run.id,
        "source": run.source.key,
        "status": run.status,
        "verdict": run.verdict,
        "mapping_version": run.mapping.version if run.mapping else None,
        "started_at": run.started_at,
        "duration_ms": run.duration_ms,
        "records_read": run.records_read,
        "records_published": run.records_published,
        "records_quarantined": run.records_quarantined,
        "drift_detected": run.drift_detected,
        "cost_usd": str(run.cost_usd),
        "error": run.error,
    }


def run_detail(run: IngestionRun) -> dict:
    return {
        **run_summary(run),
        "report": run.report,
        "events": [event_json(e) for e in run.events.all()],
        "heal_attempts": [heal_json(h) for h in run.heal_attempts.all()],
        "records": [record_json(r) for r in run.records.all()[:200]],
    }


def source_json(source: Source) -> dict:
    active = source.active_mapping
    latest = source.runs.first()
    return {
        "key": source.key,
        "name": source.name,
        "kind": source.kind,
        "enabled": source.enabled,
        "config": {k: v for k, v in source.config.items() if k != "inline"},
        "contract": contract_json(source.contract),
        "active_mapping": mapping_json(active) if active else None,
        "mapping_count": source.mappings.count(),
        "baseline": {
            "records": (source.fixtures.first().records if source.fixtures.exists() else []),
            "pinned": (source.fixtures.first().pinned if source.fixtures.exists() else False),
            "name": (source.fixtures.first().name if source.fixtures.exists() else None),
        },
        "latest_run": run_summary(latest) if latest else None,
    }
