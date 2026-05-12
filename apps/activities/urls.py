from django.urls import path

from . import views

urlpatterns = [
    path("log/<int:company_pk>/<str:channel>/", views.log_activity_view, name="log-activity"),
]
