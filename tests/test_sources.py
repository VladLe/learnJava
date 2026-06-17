import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from newsroom.sources.rss import RssFetcher, _parse_date


class _Entry(dict):
    """Minimal feedparser entry mock: supports both dict .get() and attr access."""
    def __getattr__(self, name):
        return self.get(name)


def _make_feed(entries, bozo=False):
    class _Feed:
        bozo = False
        bozo_exception = None
    f = _Feed()
    f.bozo = bozo
    f.entries = entries
    return f


@pytest.mark.django_db
def test_rss_fetcher_returns_items(target_site):
    from newsroom.models import Source
    source = Source.objects.create(name="Feed", url="https://feed.example.com/rss", target_site=target_site)

    entry = _Entry(link="https://example.com/article-1", id="uid-1", title="Article 1", summary="Sum")
    entry["published_parsed"] = None
    entry["updated_parsed"] = None

    with patch("newsroom.sources.rss.feedparser.parse", return_value=_make_feed([entry])):
        items = RssFetcher().fetch(source)

    assert len(items) == 1
    assert items[0].url == "https://example.com/article-1"
    assert items[0].guid == "uid-1"
    assert items[0].title == "Article 1"
    assert items[0].summary == "Sum"
    assert items[0].published_at is None


@pytest.mark.django_db
def test_rss_fetcher_skips_entries_without_link(target_site):
    from newsroom.models import Source
    source = Source.objects.create(name="Feed", url="https://feed.example.com/rss", target_site=target_site)

    entry = _Entry(id="uid-1", title="No URL")
    with patch("newsroom.sources.rss.feedparser.parse", return_value=_make_feed([entry])):
        items = RssFetcher().fetch(source)

    assert items == []


@pytest.mark.django_db
def test_rss_fetcher_falls_back_to_url_as_guid(target_site):
    from newsroom.models import Source
    source = Source.objects.create(name="Feed", url="https://feed.example.com/rss", target_site=target_site)

    entry = _Entry(link="https://example.com/a", title="T")
    with patch("newsroom.sources.rss.feedparser.parse", return_value=_make_feed([entry])):
        items = RssFetcher().fetch(source)

    assert items[0].guid == "https://example.com/a"


def test_parse_date_from_published_parsed():
    entry = _Entry()
    entry["published_parsed"] = time.struct_time((2024, 5, 1, 12, 0, 0, 0, 0, 0))
    result = _parse_date(entry)
    assert result == datetime(2024, 5, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_parse_date_returns_none_when_missing():
    entry = _Entry()
    assert _parse_date(entry) is None
