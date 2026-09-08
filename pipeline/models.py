from __future__ import annotations

from django.db import models

from sources.models import Mapping, Source


class IngestionRun(models.Model):
    """One attempt to read a source and publish records against its contract."""

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        PUBLISHED = "published", "Published"
        HEALED = "healed", "Healed and published"
        BLOCKED = "blocked", "Blocked -- failed closed"
        ERROR = "error", "Error"

    source = models.ForeignKey(Source, related_name="runs", on_delete=models.CASCADE)
    mapping = models.ForeignKey(
        Mapping, null=True, blank=True, related_name="runs", on_delete=models.SET_NULL
    )

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RUNNING)
    verdict = models.CharField(max_length=10, blank=True)  # pass | partial | drift

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    records_read = models.PositiveIntegerField(default=0)
    records_published = models.PositiveIntegerField(default=0)
    records_quarantined = models.PositiveIntegerField(default=0)

    drift_detected = models.BooleanField(default=False)
    report = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        return f"run#{self.pk} {self.source.key} [{self.status}]"

    @property
    def duration_ms(self) -> int | None:
        if not self.finished_at:
            return None
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


class ExtractedRecord(models.Model):
    class Status(models.TextChoices):
        PUBLISHED = "published", "Published"
        QUARANTINED = "quarantined", "Quarantined"
        WITHHELD = "withheld", "Withheld -- batch failed closed"

    run = models.ForeignKey(IngestionRun, related_name="records", on_delete=models.CASCADE)
    index = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices)

    raw = models.JSONField(default=dict)
    value = models.JSONField(default=dict)
    violations = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["index"]
        indexes = [models.Index(fields=["run", "status"])]


class RunEvent(models.Model):
    """Append-only narration of a run.

    Persisted rather than logged so the UI can replay exactly what the pipeline
    decided and in what order, after the fact and without a live connection.
    """

    class Level(models.TextChoices):
        INFO = "info", "Info"
        WARN = "warn", "Warning"
        BLOCK = "block", "Blocked"
        OK = "ok", "Success"

    run = models.ForeignKey(IngestionRun, related_name="events", on_delete=models.CASCADE)
    seq = models.PositiveIntegerField()
    at = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=8, choices=Level.choices, default=Level.INFO)
    code = models.SlugField(max_length=60)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["seq"]
        constraints = [
            models.UniqueConstraint(fields=["run", "seq"], name="uniq_event_seq_per_run"),
        ]

    def __str__(self) -> str:
        return f"[{self.run_id}:{self.seq}] {self.code}"


class HealAttempt(models.Model):
    """One proposal to repair a mapping, and the proof that decided its fate.

    Kept whether it was promoted or rejected. A rejected attempt is the more
    interesting record: it is evidence the proof gate did its job.
    """

    class Outcome(models.TextChoices):
        PROMOTED = "promoted", "Promoted"
        REJECTED = "rejected", "Rejected by the proof gate"
        FAILED = "failed", "Healer could not produce a candidate"

    run = models.ForeignKey(IngestionRun, related_name="heal_attempts", on_delete=models.CASCADE)
    source = models.ForeignKey(Source, related_name="heal_attempts", on_delete=models.CASCADE)
    attempt = models.PositiveIntegerField(default=1)

    from_mapping = models.ForeignKey(
        Mapping, null=True, blank=True, related_name="heals_from", on_delete=models.SET_NULL
    )
    candidate = models.ForeignKey(
        Mapping, null=True, blank=True, related_name="heals_to", on_delete=models.SET_NULL
    )

    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    reason = models.TextField(blank=True)

    fixtures_total = models.PositiveIntegerField(default=0)
    fixtures_passed = models.PositiveIntegerField(default=0)
    fixture_results = models.JSONField(default=list, blank=True)

    model = models.CharField(max_length=80, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["attempt"]

    def __str__(self) -> str:
        return f"heal#{self.pk} {self.source.key} -> {self.outcome}"
