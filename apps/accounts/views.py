from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.leads.views import ALL_COLUMNS, DEFAULT_LIST_COLUMNS, _get_prefs


@login_required
def save_columns_view(request):
    if request.method == "POST":
        valid_keys = {c["key"] for c in ALL_COLUMNS}
        cols = [c for c in request.POST.getlist("columns") if c in valid_keys]
        prefs = _get_prefs(request.user)
        prefs.list_columns = cols or list(DEFAULT_LIST_COLUMNS)
        prefs.save(update_fields=["list_columns"])
    return HttpResponseRedirect(request.POST.get("next", reverse("lead-list")))
