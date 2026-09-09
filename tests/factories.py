"""Shared test data: one CSV source, and the three shapes it takes."""
from __future__ import annotations

from contracts.models import Contract, ContractField
from sources.models import Mapping, Source

GOOD_CSV = """sku,produto,preco
A1,Teclado,199.90
B2,Monitor,1250.00
C3,Mouse,89.90
D4,Headset,349.00
"""

# Same facts, new packaging -- the CSV version of a site redesign.
RENAMED_CSV = """codigo,titulo,valor
A1,Teclado,199.90
B2,Monitor,1250.00
C3,Mouse,89.90
D4,Headset,349.00
"""

# Redesigned *and* repriced, which is the ordinary case in the wild.
RENAMED_REPRICED_CSV = """codigo,titulo,valor
A1,Teclado,249.90
B2,Monitor,1399.00
C3,Mouse,79.90
D4,Headset,399.00
"""

GOOD_RULES = {
    "sku": {"column": "sku"},
    "name": {"column": "produto"},
    "price": {"column": "preco"},
}
HEALED_RULES = {
    "sku": {"column": "codigo"},
    "name": {"column": "titulo"},
    "price": {"column": "valor"},
}


def make_source() -> Source:
    contract = Contract.objects.create(
        key="produtos", name="Catálogo de produtos", min_records=3,
        unique_by=["sku"], continuity_threshold=0.8,
    )
    ContractField.objects.create(
        contract=contract, name="sku", type="string", order=0, stable=True,
        description="the product code", min_fill_rate=0.9, min_distinct_ratio=0.9,
    )
    ContractField.objects.create(
        contract=contract, name="name", type="string", order=1, stable=True,
        description="the product name", min_fill_rate=0.9, min_distinct_ratio=0.5,
    )
    ContractField.objects.create(
        contract=contract, name="price", type="number", order=2, min_value=0,
        description="the price in BRL", min_fill_rate=0.8,
    )

    source = Source.objects.create(
        contract=contract, key="catalogo", name="Catálogo CSV",
        kind=Source.Kind.CSV, config={"inline": GOOD_CSV},
    )
    Mapping.objects.create(
        source=source, version=1, status=Mapping.Status.ACTIVE, rules=GOOD_RULES,
    )
    return source
