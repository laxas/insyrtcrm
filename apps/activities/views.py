from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.leads.models import Company

from .forms import EmailActivityForm, LetterActivityForm, LinkedInActivityForm, PhoneActivityForm
from .models import Activity

CHANNEL_FORMS = {
    Activity.Channel.PHONE: PhoneActivityForm,
    Activity.Channel.LINKEDIN: LinkedInActivityForm,
    Activity.Channel.EMAIL: EmailActivityForm,
    Activity.Channel.LETTER: LetterActivityForm,
}

CHANNEL_TEMPLATES = {
    Activity.Channel.PHONE: "activities/log_phone.html",
    Activity.Channel.LINKEDIN: "activities/log_linkedin.html",
    Activity.Channel.EMAIL: "activities/log_email.html",
    Activity.Channel.LETTER: "activities/log_letter.html",
}


@login_required
def log_activity_view(request, company_pk: int, channel: str):
    company = get_object_or_404(Company, pk=company_pk)
    channel = channel.upper()

    form_class = CHANNEL_FORMS.get(channel)
    if form_class is None:
        messages.error(request, _("Unknown channel."))
        return HttpResponseRedirect(reverse("lead-detail", kwargs={"pk": company_pk}))

    template = CHANNEL_TEMPLATES[channel]

    if request.method == "POST":
        form = form_class(company, request.POST)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.company = company
            activity.channel = channel
            activity.performed_by = request.user
            activity.save()
            messages.success(request, _("Activity logged."))
            if request.headers.get("HX-Request"):
                # Return a minimal response that triggers a page reload via HTMX
                from django.http import HttpResponse

                response = HttpResponse()
                response["HX-Redirect"] = reverse("lead-detail", kwargs={"pk": company_pk})
                return response
            return HttpResponseRedirect(reverse("lead-detail", kwargs={"pk": company_pk}))
    else:
        form = form_class(company)

    return render(
        request,
        template,
        {
            "company": company,
            "form": form,
            "channel": channel,
        },
    )
