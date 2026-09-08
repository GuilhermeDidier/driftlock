"""Create the demo contract, source and starting mapping.

Intentionally does not run an ingestion. The demo reads better when the first
thing a visitor does is run the pipeline while it still works -- that clean run
is what earns the source its trusted records, and nothing can be promoted
before it. Making that the first step teaches the idea instead of hiding it.
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from contracts.models import Contract, ContractField
from demo.models import DemoState
from sources.models import Source

CONTRACT_KEY = "loja"
SOURCE_KEY = "loja-exemplo"

FIELDS = [
    dict(name="sku", type="string", stable=True, order=0,
         description="the product code shown on the card, e.g. TEC-001",
         min_fill_rate=0.9, min_distinct_ratio=0.9),
    dict(name="name", type="string", stable=True, order=1,
         description="the product name as displayed to a shopper",
         min_fill_rate=0.9, min_distinct_ratio=0.5),
    dict(name="price", type="number", stable=False, order=2, min_value=0,
         description="the current selling price in BRL, however it is written",
         min_fill_rate=0.8),
    dict(name="url", type="url", stable=True, order=3,
         description="link to the product's own page",
         min_fill_rate=0.9, min_distinct_ratio=0.9),
]

# The mapping that reads the original layout.
V1_RULES = {
    "__row__": {"selector": ".product-card"},
    "sku": {"selector": ".sku", "attr": "text"},
    "name": {"selector": ".title", "attr": "text"},
    "price": {"selector": ".price", "attr": "text"},
    "url": {"selector": ".link", "attr": "href"},
}


class Command(BaseCommand):
    help = "Seed the demo contract, source and v1 mapping, and reset the storefront."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="delete the demo source and rebuild it from scratch")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            Source.objects.filter(key=SOURCE_KEY).delete()
            Contract.objects.filter(key=CONTRACT_KEY).delete()
            self.stdout.write("removed the previous demo source")

        contract, _ = Contract.objects.update_or_create(
            key=CONTRACT_KEY,
            defaults=dict(
                name="Catálogo da loja",
                description="Products listed on the demo storefront.",
                min_records=5, unique_by=["sku"], continuity_threshold=0.8,
            ),
        )
        for spec in FIELDS:
            ContractField.objects.update_or_create(
                contract=contract, name=spec["name"], defaults=spec,
            )

        url = f"{settings.DRIFTLOCK['DEMO_BASE_URL'].rstrip('/')}/demo/store/"
        source, _ = Source.objects.update_or_create(
            key=SOURCE_KEY,
            defaults=dict(contract=contract, name="Loja Exemplo (HTML)",
                          kind=Source.Kind.HTML, config={"url": url}, enabled=True),
        )
        if not source.mappings.exists():
            source.mappings.create(version=1, status="active", rules=V1_RULES,
                                   note="hand-written for the original layout")

        state = DemoState.current()
        state.layout = DemoState.Layout.ORIGINAL
        state.save(update_fields=["layout", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            f"seeded contract '{contract.key}' and source '{source.key}' -> {url}"
        ))
        self.stdout.write(
            "storefront reset to the original layout; run the pipeline once "
            "while it still works to establish the baseline."
        )
