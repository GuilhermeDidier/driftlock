from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("demo/", include("demo.urls")),
    # The dashboard is the built frontend; everything it needs is under /api/.
    path("", TemplateView.as_view(template_name="index.html"), name="dashboard"),
]
