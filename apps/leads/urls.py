from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="lead-list", permanent=False)),
    path("leads/", views.LeadListView.as_view(), name="lead-list"),
    path("leads/export/letter/", views.letter_export_view, name="letter-export"),
    path("leads/export/letter/log/", views.letter_log_view, name="letter-log"),
    path("leads/export/csv/", views.csv_export_view, name="csv-export"),
    path("leads/columns/", views.save_columns_view, name="save-columns"),
    path("leads/<int:pk>/", views.LeadDetailView.as_view(), name="lead-detail"),
    path("leads/<int:pk>/transition/", views.transition_view, name="lead-transition"),
    path("leads/<int:pk>/tabs/briefing/", views.tab_briefing, name="tab-briefing"),
    path("leads/<int:pk>/tabs/contacts/", views.tab_contacts, name="tab-contacts"),
    path("leads/<int:pk>/tabs/activities/", views.tab_activities, name="tab-activities"),
    path("leads/<int:pk>/tabs/history/", views.tab_history, name="tab-history"),
]
