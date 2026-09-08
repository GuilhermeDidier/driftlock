from django.urls import path

from . import views

app_name = "demo"

urlpatterns = [
    path("store/", views.store, name="store"),
]
