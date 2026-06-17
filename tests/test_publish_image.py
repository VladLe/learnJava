from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from newsroom.images.base import ImageCandidate
from newsroom.publish.wordpress import WordPressPublisher


def _site():
    return SimpleNamespace(
        base_url="https://wp.example.com/", auth_user="u", auth_app_password="p",
        default_status="draft",
    )


def _content():
    return SimpleNamespace(
        title="T", body_html="<p>B</p>", excerpt="E", tags=["news"],
    )


def _candidate():
    return ImageCandidate(
        url="https://images.pexels.com/p/1.jpg",
        alt="alt text", credit="Jane Doe",
        source_page="https://www.pexels.com/photo/1/",
    )


def test_publish_sets_featured_media_from_image():
    post_resp = MagicMock()
    post_resp.raise_for_status.return_value = None
    post_resp.json.return_value = {"id": 10, "link": "https://wp.example.com/?p=10"}

    publisher = WordPressPublisher()
    with (
        patch.object(publisher, "_ensure_tags", return_value=[]),
        patch.object(publisher, "_upload_media", return_value=77) as mock_upload,
        patch("newsroom.publish.wordpress.httpx.post", return_value=post_resp) as mock_post,
    ):
        publisher.publish(_site(), None, _content(), "https://src/1", image=_candidate())

    mock_upload.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["featured_media"] == 77


def test_publish_omits_featured_media_without_image():
    post_resp = MagicMock()
    post_resp.raise_for_status.return_value = None
    post_resp.json.return_value = {"id": 1, "link": "https://wp.example.com/?p=1"}

    publisher = WordPressPublisher()
    with (
        patch.object(publisher, "_ensure_tags", return_value=[]),
        patch("newsroom.publish.wordpress.httpx.post", return_value=post_resp) as mock_post,
    ):
        publisher.publish(_site(), None, _content(), "https://src/1", image=None)

    _, kwargs = mock_post.call_args
    assert "featured_media" not in kwargs["json"]


def test_publish_continues_when_image_upload_returns_none():
    post_resp = MagicMock()
    post_resp.raise_for_status.return_value = None
    post_resp.json.return_value = {"id": 1, "link": "https://wp.example.com/?p=1"}

    publisher = WordPressPublisher()
    with (
        patch.object(publisher, "_ensure_tags", return_value=[]),
        patch.object(publisher, "_upload_media", return_value=None),
        patch("newsroom.publish.wordpress.httpx.post", return_value=post_resp) as mock_post,
    ):
        outcome = publisher.publish(_site(), None, _content(), "https://src/1", image=_candidate())

    assert outcome.wp_post_id == 1
    _, kwargs = mock_post.call_args
    assert "featured_media" not in kwargs["json"]


# ── _upload_media ─────────────────────────────────────────────────────────────

def test_upload_media_downloads_and_uploads():
    img_resp = MagicMock()
    img_resp.raise_for_status.return_value = None
    img_resp.headers = {"content-type": "image/jpeg"}
    img_resp.content = b"\xff\xd8jpegbytes"

    media_resp = MagicMock()
    media_resp.raise_for_status.return_value = None
    media_resp.json.return_value = {"id": 88}

    meta_resp = MagicMock()

    publisher = WordPressPublisher()
    with (
        patch("newsroom.publish.wordpress.httpx.get", return_value=img_resp),
        patch("newsroom.publish.wordpress.httpx.post", side_effect=[media_resp, meta_resp]) as mock_post,
    ):
        media_id = publisher._upload_media("https://wp.example.com", ("u", "p"), _candidate())

    assert media_id == 88
    # first post is the media upload with binary content
    first_call = mock_post.call_args_list[0]
    assert first_call.args[0].endswith("/wp-json/wp/v2/media")
    assert first_call.kwargs["content"] == b"\xff\xd8jpegbytes"


def test_upload_media_returns_none_on_download_error():
    publisher = WordPressPublisher()
    with patch("newsroom.publish.wordpress.httpx.get", side_effect=httpx.ConnectError("x")):
        assert publisher._upload_media("https://wp.example.com", ("u", "p"), _candidate()) is None


def test_upload_media_returns_none_on_upload_error():
    img_resp = MagicMock()
    img_resp.raise_for_status.return_value = None
    img_resp.headers = {"content-type": "image/jpeg"}
    img_resp.content = b"bytes"

    publisher = WordPressPublisher()
    with (
        patch("newsroom.publish.wordpress.httpx.get", return_value=img_resp),
        patch("newsroom.publish.wordpress.httpx.post", side_effect=httpx.ConnectError("x")),
    ):
        assert publisher._upload_media("https://wp.example.com", ("u", "p"), _candidate()) is None
