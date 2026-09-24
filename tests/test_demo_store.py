"""The demo storefront is the page the healer reads.

Anything a template leaks into it, the model sees. A broken {# #} comment once
rendered the answer to the silent break (".price became .amount") into every
card of layout v3.
"""
from __future__ import annotations

import pytest

from demo.models import DemoState


@pytest.mark.parametrize("layout", [choice for choice, _ in DemoState.Layout.choices])
def test_store_renders_no_template_syntax(client, db, layout):
    state = DemoState.current()
    state.layout = layout
    state.save()
    html = client.get("/demo/store/").content.decode()
    assert "Teclado Mecânico RGB" in html
    for token in ("{#", "#}", "{%", "{{"):
        assert token not in html, f"layout {layout} renders {token!r}"
