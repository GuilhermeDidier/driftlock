from django.urls import path

from . import views

urlpatterns = [
    path("state/", views.state, name="state"),
    path("sources/<slug:key>/", views.source_detail, name="source-detail"),
    path("sources/<slug:key>/run/", views.trigger_run, name="source-run"),
    path("runs/<int:run_id>/", views.run_view, name="run-detail"),
    path("demo/layout/", views.demo_layout, name="demo-layout"),
]
