from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("activities/", include("apps.activities.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("stats/", include("apps.stats.urls")),
    path("", include("apps.leads.urls")),  # root → redirect at "" in leads/urls.py
]
