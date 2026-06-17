from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from newsroom.publish.base import PublishError, PublishOutcome
from newsroom.publish.wordpress import WordPressPublisher


def _site():
    return SimpleNamespace(
        base_url="https://wp.example.com/",
        auth_user="admin",
        auth_app_password="secret",
        default_status="draft",
    )


def _content():
    return SimpleNamespace(
        title="New Title",
        body_html="<p>Body.</p>",
        excerpt="Excerpt.",
        tags=["tag1", "tag2"],
    )


def _category(wp_id=5):
    return SimpleNamespace(wp_category_id=wp_id, name="Tech")


# ── publish ───────────────────────────────────────────────────────────────────

def test_publish_returns_outcome():
    post_resp = MagicMock()
    post_resp.raise_for_status.return_value = None
    post_resp.json.return_value = {"id": 42, "link": "https://wp.example.com/?p=42"}

    publisher = WordPressPublisher()
    with (
        patch.object(publisher, "_ensure_tags", return_value=[1, 2]),
        patch("newsroom.publish.wordpress.httpx.post", return_value=post_resp) as mock_post,
    ):
        outcome = publisher.publish(_site(), _category(), _content(), "https://src.example.com/1")

    assert isinstance(outcome, PublishOutcome)
    assert outcome.wp_post_id == 42
    assert outcome.wp_url == "https://wp.example.com/?p=42"

    # category id and status went into the payload
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["categories"] == [5]
    assert kwargs["json"]["status"] == "draft"
    assert kwargs["json"]["tags"] == [1, 2]


def test_publish_without_category_omits_categories():
    post_resp = MagicMock()
    post_resp.raise_for_status.return_value = None
    post_resp.json.return_value = {"id": 1, "link": "https://wp.example.com/?p=1"}

    publisher = WordPressPublisher()
    with (
        patch.object(publisher, "_ensure_tags", return_value=[]),
        patch("newsroom.publish.wordpress.httpx.post", return_value=post_resp) as mock_post,
    ):
        publisher.publish(_site(), None, _content(), "https://src.example.com/1")

    _, kwargs = mock_post.call_args
    assert "categories" not in kwargs["json"]


def test_publish_custom_status_passed_through():
    post_resp = MagicMock()
    post_resp.raise_for_status.return_value = None
    post_resp.json.return_value = {"id": 1, "link": "https://wp.example.com/?p=1"}

    publisher = WordPressPublisher()
    with (
        patch.object(publisher, "_ensure_tags", return_value=[]),
        patch("newsroom.publish.wordpress.httpx.post", return_value=post_resp) as mock_post,
    ):
        publisher.publish(_site(), None, _content(), "https://src.example.com/1", status="publish")

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["status"] == "publish"


def test_publish_raises_publish_error_on_http_status():
    err_resp = MagicMock()
    err_resp.status_code = 401
    err_resp.text = "Unauthorized"
    status_error = httpx.HTTPStatusError("401", request=MagicMock(), response=err_resp)

    post_resp = MagicMock()
    post_resp.raise_for_status.side_effect = status_error

    publisher = WordPressPublisher()
    with (
        patch.object(publisher, "_ensure_tags", return_value=[]),
        patch("newsroom.publish.wordpress.httpx.post", return_value=post_resp),
    ):
        with pytest.raises(PublishError, match="401"):
            publisher.publish(_site(), None, _content(), "https://src.example.com/1")


def test_publish_raises_publish_error_on_connection_error():
    publisher = WordPressPublisher()
    with (
        patch.object(publisher, "_ensure_tags", return_value=[]),
        patch("newsroom.publish.wordpress.httpx.post", side_effect=httpx.ConnectError("refused")),
    ):
        with pytest.raises(PublishError, match="connection error"):
            publisher.publish(_site(), None, _content(), "https://src.example.com/1")


# ── _ensure_tags ──────────────────────────────────────────────────────────────

def test_ensure_tags_creates_new():
    created = MagicMock()
    created.status_code = 201
    created.json.return_value = {"id": 10}

    publisher = WordPressPublisher()
    with patch("newsroom.publish.wordpress.httpx.post", return_value=created):
        ids = publisher._ensure_tags("https://wp.example.com", ("u", "p"), ["news"])

    assert ids == [10]


def test_ensure_tags_handles_existing_term():
    existing = MagicMock()
    existing.status_code = 400
    existing.json.return_value = {"code": "term_exists", "data": {"term_id": 7}}

    publisher = WordPressPublisher()
    with patch("newsroom.publish.wordpress.httpx.post", return_value=existing):
        ids = publisher._ensure_tags("https://wp.example.com", ("u", "p"), ["news"])

    assert ids == [7]


def test_ensure_tags_skips_on_error():
    publisher = WordPressPublisher()
    with patch("newsroom.publish.wordpress.httpx.post", side_effect=httpx.ConnectError("x")):
        ids = publisher._ensure_tags("https://wp.example.com", ("u", "p"), ["news"])

    assert ids == []


# ── check_connection ──────────────────────────────────────────────────────────

def test_check_connection_ok():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    with patch("newsroom.publish.wordpress.httpx.get", return_value=resp):
        WordPressPublisher.check_connection(_site())  # no raise


def test_check_connection_raises():
    with patch("newsroom.publish.wordpress.httpx.get", side_effect=httpx.ConnectError("x")):
        with pytest.raises(PublishError, match="Connection failed"):
            WordPressPublisher.check_connection(_site())


# ── sync_categories ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_sync_categories_upserts(target_site):
    from newsroom.models import WordPressCategory

    page1 = MagicMock()
    page1.raise_for_status.return_value = None
    page1.json.return_value = [
        {"id": 1, "name": "Tech", "slug": "tech"},
        {"id": 2, "name": "News", "slug": "news"},
    ]

    with patch("newsroom.publish.wordpress.httpx.get", return_value=page1):
        count = WordPressPublisher.sync_categories(target_site)

    assert count == 2
    assert WordPressCategory.objects.filter(site=target_site).count() == 2
