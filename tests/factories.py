import factory
from django.contrib.auth.models import User
from django.utils import timezone

from apps.activities.models import Activity
from apps.leads.models import Company, Contact, PRBriefing, Stage


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpassword123!")
    is_active = True


class StageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Stage

    name_de = factory.Sequence(lambda n: f"Stage DE {n}")
    name_en = factory.Sequence(lambda n: f"Stage EN {n}")
    order = factory.Sequence(lambda n: n + 10)
    is_final = False
    is_archive = False


class CompanyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Company

    name = factory.Sequence(lambda n: f"Company {n}")
    domain = factory.Sequence(lambda n: f"company{n}.com")


class ContactFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Contact

    company = factory.SubFactory(CompanyFactory)
    full_name = factory.Sequence(lambda n: f"Contact {n}")
    email = factory.Sequence(lambda n: f"contact{n}@example.com")


class PRBriefingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PRBriefing

    company = factory.SubFactory(CompanyFactory)
    reality_check = "Some reality check text"
    ai_perception = "Some AI perception text"
    media_hook = "Some media hook"
    story_potential = 3
    fit_score = 4
    priority = PRBriefing.Priority.A


class ActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Activity

    company = factory.SubFactory(CompanyFactory)
    channel = Activity.Channel.PHONE
    direction = Activity.Direction.OUT
    outcome = Activity.Outcome.INTERESTED
    occurred_at = factory.LazyFunction(timezone.now)
    performed_by = factory.SubFactory(UserFactory)
    note = "Test note"
