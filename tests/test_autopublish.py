from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from newsroom.models import Article, Publication, Source, TargetSite
from newsroom.publish.base import PublishError
from newsroom.publish.wordpress import WordPressPublisher


def _site():
    return SimpleNamespace(
        base_url="https://wp.example.com/", auth_user="u", auth_app_password="p"
    )


# ── update_status ─────────────────────────────────────────────────────────────

def test_update_status_posts_new_status():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    with patch("newsroom.publish.wordpress.httpx.post", return_value=resp) as mock_post:
        WordPressPublisher.update_status(_site(), 42, "publish")

    args, kwargs = mock_post.call_args
    assert args[0].endswith("/wp-json/wp/v2/posts/42")
    assert kwargs["json"] == {"status": "publish"}


def test_update_status_raises_on_error():
    with patch("newsroom.publish.wordpress.httpx.post", side_effect=httpx.ConnectError("x")):
        with pytest.raises(PublishError):
            WordPressPublisher.update_status(_site(), 1, "publish")


# ── TargetSite autopublish toggle ─────────────────────────────────────────────

@pytest.mark.django_db
def test_enable_autopublish_action(admin_client, target_site):
    assert target_site.default_status == "draft"
    admin_client.post(
        "/admin/newsroom/targetsite/",
        {"action": "action_enable_autopublish", "_selected_action": [target_site.pk]},
    )
    target_site.refresh_from_db()
    assert target_site.default_status == TargetSite.Status.PUBLISH


@pytest.mark.django_db
def test_disable_autopublish_action(admin_client, target_site):
    target_site.default_status = TargetSite.Status.PUBLISH
    target_site.save()
    admin_client.post(
        "/admin/newsroom/targetsite/",
        {"action": "action_disable_autopublish", "_selected_action": [target_site.pk]},
    )
    target_site.refresh_from_db()
    assert target_site.default_status == TargetSite.Status.DRAFT


# ── Publication promote action ────────────────────────────────────────────────

@pytest.mark.django_db
def test_promote_to_publish_action(admin_client, target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    article = Article.objects.create(
        source=source, guid="g1", source_url="https://example.com/1",
        url_hash="a" * 64, original_title="A", status=Article.Status.PUBLISHED,
    )
    pub = Publication.objects.create(
        article=article, target_site=target_site,
        wp_post_id=55, status=Publication.Status.PUBLISHED,
    )

    with patch("newsroom.admin.WordPressPublisher.update_status") as mock_update:
        admin_client.post(
            "/admin/newsroom/publication/",
            {"action": "action_promote_to_publish", "_selected_action": [pub.pk]},
        )

    mock_update.assert_called_once_with(target_site, 55, "publish")
