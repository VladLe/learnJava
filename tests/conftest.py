import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def admin_user(db):
    User = get_user_model()
    return User.objects.create_superuser("admin", "admin@example.com", "password")


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def target_site(db):
    from newsroom.models import TargetSite

    return TargetSite.objects.create(
        name="Test WP Site",
        base_url="https://wp.example.com",
        auth_user="wpuser",
        auth_app_password="wppassword",
    )
