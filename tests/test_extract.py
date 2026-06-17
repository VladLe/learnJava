from unittest.mock import MagicMock, patch

import httpx
import pytest

from newsroom.extract.article import ExtractionError, extract_text


def _ok_response(html):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.text = html
    return resp


def test_extract_text_success():
    html = "<html><body><article><p>Main content here.</p></article></body></html>"
    with (
        patch("newsroom.extract.article.httpx.get", return_value=_ok_response(html)),
        patch("newsroom.extract.article.trafilatura.extract", return_value="Main content here."),
    ):
        result = extract_text("https://example.com/article")
    assert result == "Main content here."


def test_extract_text_sends_user_agent():
    with (
        patch("newsroom.extract.article.httpx.get", return_value=_ok_response("<html></html>")) as mock_get,
        patch("newsroom.extract.article.trafilatura.extract", return_value="text"),
    ):
        extract_text("https://example.com/article")
    _, kwargs = mock_get.call_args
    assert "User-Agent" in kwargs["headers"]
    assert kwargs["follow_redirects"] is True


def test_extract_text_raises_when_download_fails():
    with patch("newsroom.extract.article.httpx.get", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(ExtractionError, match="Could not download"):
            extract_text("https://example.com/unreachable")


def test_extract_text_raises_on_http_error_status():
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403", request=MagicMock(), response=MagicMock()
    )
    with patch("newsroom.extract.article.httpx.get", return_value=resp):
        with pytest.raises(ExtractionError, match="Could not download"):
            extract_text("https://example.com/forbidden")


def test_extract_text_raises_when_no_text():
    with (
        patch("newsroom.extract.article.httpx.get", return_value=_ok_response("<html></html>")),
        patch("newsroom.extract.article.trafilatura.extract", return_value=None),
    ):
        with pytest.raises(ExtractionError, match="No text could be extracted"):
            extract_text("https://example.com/empty")


def test_extract_text_raises_when_extract_returns_empty_string():
    with (
        patch("newsroom.extract.article.httpx.get", return_value=_ok_response("<html></html>")),
        patch("newsroom.extract.article.trafilatura.extract", return_value=""),
    ):
        with pytest.raises(ExtractionError):
            extract_text("https://example.com/empty")
