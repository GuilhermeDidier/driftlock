from __future__ import annotations

from django.db import models

from contracts.models import Contract


class Source(models.Model):
    """Where records come from, and how to reach it."""

    class Kind(models.TextChoices):
        HTML = "html", "HTML page"
        CSV = "csv", "CSV file"

    contract = models.ForeignKey(Contract, related_name="sources", on_delete=models.CASCADE)
    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=Kind.choices)

    # Adapter-specific settings: {"url": ...} for html, {"path"|"url": ...} for csv.
    config = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key

    @property
    def active_mapping(self) -> "Mapping | None":
        return self.mappings.filter(status=Mapping.Status.ACTIVE).order_by("-version").first()


class Mapping(models.Model):
    """A versioned recipe for reading one source into contract fields.

    Never edited in place. A heal produces a CANDIDATE; only a candidate that
    reproduces the golden fixtures is promoted to ACTIVE, and the mapping it
    replaces is retired rather than deleted so a rollback is always one row
    away.
    """

    class Status(models.TextChoices):
        CANDIDATE = "candidate", "Candidate"
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"
        REJECTED = "rejected", "Rejected"

    class Origin(models.TextChoices):
        HUMAN = "human", "Authored by a human"
        HEAL = "heal", "Proposed by the healer"

    source = models.ForeignKey(Source, related_name="mappings", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CANDIDATE)
    origin = models.CharField(max_length=8, choices=Origin.choices, default=Origin.HUMAN)

    # field name -> extraction rule. Shape depends on the adapter:
    #   html: {"selector": ".price", "attr": "text"}
    #   csv:  {"column": "Preco"}
    rules = models.JSONField(default=dict)

    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="children", on_delete=models.SET_NULL
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    promoted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["source", "version"], name="uniq_mapping_version"),
        ]

    def __str__(self) -> str:
        return f"{self.source.key} v{self.version} ({self.status})"

    def diff_against(self, other: "Mapping | None") -> dict[str, dict]:
        """Field-by-field changes, for the audit trail."""
        before = (other.rules if other else {}) or {}
        changes: dict[str, dict] = {}
        for name in sorted(set(before) | set(self.rules or {})):
            was, now = before.get(name), (self.rules or {}).get(name)
            if was != now:
                changes[name] = {"before": was, "after": now}
        return changes


class GoldenFixture(models.Model):
    """Records already known to be correct for this source.

    Not a saved payload to replay -- see engine/continuity.py for why replay
    cannot work across a genuine change of shape. A fixture is the *answer*:
    the records a correct mapping must still recover.

    Pinned fixtures are confirmed by a human and never expire. Unpinned ones
    are captured automatically from the most recent successful run, so a source
    that has run cleanly even once has something to be held to.
    """

    source = models.ForeignKey(Source, related_name="fixtures",
                               on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    records = models.JSONField(default=list)

    # Kept for the audit trail only: what the payload looked like when these
    # records were confirmed. Never used to judge a candidate.
    raw = models.TextField(blank=True)

    pinned = models.BooleanField(default=False)
    captured_at = models.DateTimeField(auto_now_add=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["-pinned", "-captured_at"]

    def __str__(self) -> str:
        kind = "pinned" if self.pinned else "captured"
        return f"{self.source.key}: {self.name} ({kind})"
