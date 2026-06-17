import pytest

from newsroom.models import Article, Source, TargetSite


@pytest.mark.django_db
def test_target_site_str():
    site = TargetSite(name="My Blog", base_url="https://example.com")
    assert str(site) == "My Blog"


@pytest.mark.django_db
def test_article_status_choices():
    choices = {c[0] for c in Article.Status.choices}
    assert {
        "fetched", "extracted", "rewritten", "pending", "rejected",
        "published", "failed", "skipped",
    } == choices


@pytest.mark.django_db
def test_create_target_site(db):
    site = TargetSite.objects.create(
        name="Test Site",
        base_url="https://test.example.com",
        auth_user="admin",
        auth_app_password="secret",
    )
    assert site.pk is not None
    assert site.default_status == "draft"
    assert site.enabled is True
