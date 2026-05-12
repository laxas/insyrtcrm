from django.urls import path

from . import views

urlpatterns = [
    path("preferences/columns/", views.save_columns_view, name="save-columns"),
]
