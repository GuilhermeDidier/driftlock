from __future__ import annotations

from django.shortcuts import render

from .catalog import PRODUCTS
from .models import DemoState


def _ptbr(value: float) -> str:
    """1899.0 -> '1.899,00'. The redesign also changes how prices are written."""
    whole, _, cents = f"{value:,.2f}".partition(".")
    return f"{whole.replace(',', '.')},{cents}"


def store(request):
    """The demo storefront, rendered in whichever layout is currently active."""
    state = DemoState.current()
    products = [{**p, "price_ptbr": _ptbr(p["price"])} for p in PRODUCTS]
    template = f"demo/store_{state.layout}.html"
    return render(request, template, {"products": products, "layout": state.layout})
