import json
from unittest.mock import MagicMock, patch

import pytest

from newsroom.models import Article, Source, TargetSite, WordPressCategory


# ── categories-by-site endpoint ───────────────────────────────────────────────

@pytest.mark.django_db
def test_categories_by_site_returns_filtered(admin_client, target_site):
    WordPressCategory.objects.create(site=target_site, wp_category_id=1, name="Tech", slug="tech")
    WordPressCategory.objects.create(site=target_site, wp_category_id=2, name="News", slug="news")

    other_site = TargetSite.objects.create(
        name="Other", base_url="https://other.example.com",
        auth_user="u", auth_app_password="p",
    )
    WordPressCategory.objects.create(site=other_site, wp_category_id=99, name="Misc", slug="misc")

    url = f"/admin/newsroom/source/categories-by-site/?site_id={target_site.pk}"
    resp = admin_client.get(url)
    assert resp.status_code == 200
    data = json.loads(resp.content)
    names = {c["name"] for c in data["categories"]}
    assert names == {"Tech", "News"}


@pytest.mark.django_db
def test_categories_by_site_empty_without_site(admin_client):
    resp = admin_client.get("/admin/newsroom/source/categories-by-site/")
    assert resp.status_code == 200
    assert json.loads(resp.content) == {"categories": []}


# ── action_retry ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_retry_action_resets_failed_articles(admin_client, target_site):
    source = Source.objects.create(
        name="Feed", url="https://feed.example.com/rss", target_site=target_site
    )
    failed = Article.objects.create(
        source=source, guid="g1", source_url="https://src.example.com/1",
        url_hash="hash1", original_title="Article 1",
        status=Article.Status.FAILED, error="timeout",
    )
    published = Article.objects.create(
        source=source, guid="g2", source_url="https://src.example.com/2",
        url_hash="hash2", original_title="Article 2",
        status=Article.Status.PUBLISHED,
    )

    resp = admin_client.post(
        "/admin/newsroom/article/",
        {
            "action": "action_retry",
            "_selected_action": [failed.pk, published.pk],
        },
    )
    assert resp.status_code in (200, 302)

    failed.refresh_from_db()
    published.refresh_from_db()
    assert failed.status == Article.Status.FETCHED
    assert failed.error == ""
    assert published.status == Article.Status.PUBLISHED  # unchanged


# ── sync_categories action (mocked HTTP) ─────────────────────────────────────

@pytest.mark.django_db
def test_sync_categories_action_upserts(admin_client, target_site):
    fake_categories = [
        {"id": 1, "name": "Tech", "slug": "tech"},
        {"id": 2, "name": "Sports", "slug": "sports"},
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_categories
    mock_resp.raise_for_status.return_value = None

    with patch("newsroom.admin.httpx.get", return_value=mock_resp):
        resp = admin_client.post(
            "/admin/newsroom/targetsite/",
            {
                "action": "action_sync_categories",
                "_selected_action": [target_site.pk],
            },
        )
    assert resp.status_code in (200, 302)
    assert WordPressCategory.objects.filter(site=target_site).count() == 2
    assert WordPressCategory.objects.get(site=target_site, wp_category_id=1).name == "Tech"


# ── admin pages load ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_admin_changelist_pages_load(admin_client):
    for url in [
        "/admin/newsroom/targetsite/",
        "/admin/newsroom/wordpresscategory/",
        "/admin/newsroom/source/",
        "/admin/newsroom/article/",
        "/admin/newsroom/publication/",
    ]:
        resp = admin_client.get(url)
        assert resp.status_code == 200, f"Failed for {url}"
