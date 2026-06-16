from unittest.mock import patch

import pytest

from newsroom.extract.article import ExtractionError, extract_text


def test_extract_text_success():
    html = "<html><body><article><p>Main content here.</p></article></body></html>"
    with (
        patch("newsroom.extract.article.trafilatura.fetch_url", return_value=html),
        patch("newsroom.extract.article.trafilatura.extract", return_value="Main content here."),
    ):
        result = extract_text("https://example.com/article")
    assert result == "Main content here."


def test_extract_text_raises_when_download_fails():
    with patch("newsroom.extract.article.trafilatura.fetch_url", return_value=None):
        with pytest.raises(ExtractionError, match="Could not download"):
            extract_text("https://example.com/unreachable")


def test_extract_text_raises_when_no_text():
    with (
        patch("newsroom.extract.article.trafilatura.fetch_url", return_value="<html></html>"),
        patch("newsroom.extract.article.trafilatura.extract", return_value=None),
    ):
        with pytest.raises(ExtractionError, match="No text could be extracted"):
            extract_text("https://example.com/empty")


def test_extract_text_raises_when_extract_returns_empty_string():
    with (
        patch("newsroom.extract.article.trafilatura.fetch_url", return_value="<html></html>"),
        patch("newsroom.extract.article.trafilatura.extract", return_value=""),
    ):
        with pytest.raises(ExtractionError):
            extract_text("https://example.com/empty")
