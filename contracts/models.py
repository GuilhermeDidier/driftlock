from __future__ import annotations

from django.db import models

from .engine import ContractSpec, FieldSpec, FieldType


class Contract(models.Model):
    """The declared shape of a batch of records.

    A contract outlives any particular way of reading a source. That is the
    whole idea: extraction rules rot, the contract does not.
    """

    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    min_records = models.PositiveIntegerField(default=1)
    unique_by = models.JSONField(default=list, blank=True)
    continuity_threshold = models.FloatField(default=0.8)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key

    def to_spec(self) -> ContractSpec:
        """Project the stored contract onto the pure engine spec."""
        fields = tuple(f.to_spec() for f in self.fields.all())
        return ContractSpec(
            key=self.key,
            fields=fields,
            min_records=self.min_records,
            min_fill_rate={
                f.name: f.min_fill_rate
                for f in self.fields.all()
                if f.min_fill_rate is not None
            },
            min_distinct_ratio={
                f.name: f.min_distinct_ratio
                for f in self.fields.all()
                if f.min_distinct_ratio is not None
            },
            unique_by=tuple(self.unique_by or ()),
            continuity_threshold=self.continuity_threshold,
        )


class ContractField(models.Model):
    TYPE_CHOICES = [(t.value, t.value) for t in FieldType]

    contract = models.ForeignKey(Contract, related_name="fields", on_delete=models.CASCADE)
    name = models.SlugField(max_length=80)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=FieldType.STRING.value)

    # What the field *means*, in plain language. This is the anchor the healer
    # reasons from when the mechanical rule stops working, so it is required
    # and should read like an instruction to a careful human.
    description = models.TextField()

    required = models.BooleanField(default=True)

    # Compared when proving a healed mapping. See engine/continuity.py.
    stable = models.BooleanField(default=False)

    order = models.PositiveIntegerField(default=0)

    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)
    max_length = models.PositiveIntegerField(null=True, blank=True)
    pattern = models.CharField(max_length=200, blank=True)
    choices = models.JSONField(default=list, blank=True)

    # Batch-level thresholds. Null means "no rule for this field".
    min_fill_rate = models.FloatField(null=True, blank=True)
    min_distinct_ratio = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["contract", "name"], name="uniq_field_per_contract"),
        ]

    def __str__(self) -> str:
        return f"{self.contract.key}.{self.name}"

    def to_spec(self) -> FieldSpec:
        return FieldSpec(
            name=self.name,
            type=FieldType(self.type),
            description=self.description,
            required=self.required,
            stable=self.stable,
            min_value=self.min_value,
            max_value=self.max_value,
            max_length=self.max_length,
            pattern=self.pattern or None,
            choices=tuple(self.choices) if self.choices else None,
        )
