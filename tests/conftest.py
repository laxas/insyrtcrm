import pytest
from django.test import Client

from .factories import UserFactory


@pytest.fixture
def user(db):
    return UserFactory(is_active=True)


@pytest.fixture
def auth_client(user):
    c = Client()
    c.force_login(user)
    return c
