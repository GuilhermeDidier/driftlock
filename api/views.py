from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from demo.models import DemoState
from pipeline.models import IngestionRun
from pipeline.runner import run_ingestion
from sources.models import Source

from .serializers import mapping_json, run_detail, run_summary, source_json


@api_view(["GET"])
def state(request):
    """Everything the dashboard needs on first paint."""
    return Response({
        "demo_layout": DemoState.current().layout,
        "sources": [source_json(s) for s in Source.objects.all()],
        "recent_runs": [run_summary(r) for r in IngestionRun.objects.all()[:20]],
    })


@api_view(["GET"])
def source_detail(request, key: str):
    source = get_object_or_404(Source, key=key)
    mappings = list(source.mappings.all())
    by_id = {m.id: m for m in mappings}
    return Response({
        **source_json(source),
        "mappings": [
            mapping_json(m, by_id.get(m.parent_id) if m.parent_id else None)
            for m in mappings
        ],
        "runs": [run_summary(r) for r in source.runs.all()[:25]],
    })


@api_view(["POST"])
def trigger_run(request, key: str):
    source = get_object_or_404(Source, key=key)
    allow_heal = request.data.get("allow_heal", True)
    run = run_ingestion(source, allow_heal=bool(allow_heal))
    return Response(run_detail(run), status=201)


@api_view(["GET"])
def run_view(request, run_id: int):
    run = get_object_or_404(IngestionRun, pk=run_id)
    return Response(run_detail(run))


@api_view(["GET", "POST"])
def demo_layout(request):
    """Read or flip the storefront's markup.

    Flipping this is the whole demo: the products do not change, only the way
    the page is built. Everything downstream has to notice on its own.
    """
    state_row = DemoState.current()
    if request.method == "POST":
        layout = request.data.get("layout")
        if layout not in dict(DemoState.Layout.choices):
            return Response({"detail": "layout must be 'v1' or 'v2'"}, status=400)
        state_row.layout = layout
        state_row.save(update_fields=["layout", "updated_at"])
    return Response({"layout": state_row.layout, "updated_at": state_row.updated_at})
