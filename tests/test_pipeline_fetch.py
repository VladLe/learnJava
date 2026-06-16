from unittest.mock import patch

import pytest

from newsroom.models import Article, Source
from newsroom.sources.base import FetchedItem
from newsroom import pipeline


def _item(url, title="T", guid=None):
    return FetchedItem(guid=guid or url, url=url, title=title, summary=None, published_at=None)


@pytest.mark.django_db
def test_fetch_and_store_saves_new_articles(target_site):
    source = Source.objects.create(name="Feed", url="https://feed.example.com/rss", target_site=target_site)
    items = [_item("https://example.com/a"), _item("https://example.com/b")]

    with patch("newsroom.pipeline._fetcher.fetch", return_value=items):
        saved, skipped = pipeline.fetch_and_store(source)

    assert saved == 2
    assert skipped == 0
    assert Article.objects.filter(source=source, status="fetched").count() == 2


@pytest.mark.django_db
def test_fetch_and_store_skips_duplicates(target_site):
    source = Source.objects.create(name="Feed", url="https://feed.example.com/rss", target_site=target_site)
    item = _item("https://example.com/a")

    with patch("newsroom.pipeline._fetcher.fetch", return_value=[item]):
        pipeline.fetch_and_store(source)  # first run

    with patch("newsroom.pipeline._fetcher.fetch", return_value=[item]):
        saved, skipped = pipeline.fetch_and_store(source)  # second run

    assert saved == 0
    assert skipped == 1
    assert Article.objects.count() == 1  # no duplicate


@pytest.mark.django_db
def test_fetch_and_store_utm_dedup(target_site):
    source = Source.objects.create(name="Feed", url="https://feed.example.com/rss", target_site=target_site)
    original = _item("https://example.com/article")
    utm_version = _item("https://example.com/article?utm_source=twitter")

    with patch("newsroom.pipeline._fetcher.fetch", return_value=[original]):
        pipeline.fetch_and_store(source)

    with patch("newsroom.pipeline._fetcher.fetch", return_value=[utm_version]):
        saved, skipped = pipeline.fetch_and_store(source)

    assert saved == 0
    assert skipped == 1


@pytest.mark.django_db
def test_fetch_and_store_updates_last_fetched_at(target_site):
    source = Source.objects.create(name="Feed", url="https://feed.example.com/rss", target_site=target_site)
    assert source.last_fetched_at is None

    with patch("newsroom.pipeline._fetcher.fetch", return_value=[]):
        pipeline.fetch_and_store(source)

    source.refresh_from_db()
    assert source.last_fetched_at is not None
