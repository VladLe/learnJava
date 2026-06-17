import pytest

from newsroom.dedup import normalize_url, url_hash, is_seen
from newsroom.sources.base import FetchedItem


# ── normalize_url ─────────────────────────────────────────────────────────────

def test_normalize_strips_utm():
    url = "https://Example.COM/news/article/?utm_source=google&utm_medium=cpc&id=42"
    result = normalize_url(url)
    assert "utm_source" not in result
    assert "utm_medium" not in result
    assert "id=42" in result


def test_normalize_drops_fragment():
    result = normalize_url("https://example.com/article#comments")
    assert "#" not in result
    assert "comments" not in result


def test_normalize_strips_trailing_slash():
    assert normalize_url("https://example.com/news/") == normalize_url("https://example.com/news")


def test_normalize_lowercases_scheme_and_host():
    result = normalize_url("HTTPS://Example.COM/path")
    assert result.startswith("https://example.com/")


def test_normalize_sorts_query_params():
    a = normalize_url("https://example.com/?z=1&a=2")
    b = normalize_url("https://example.com/?a=2&z=1")
    assert a == b


# ── url_hash ──────────────────────────────────────────────────────────────────

def test_url_hash_is_deterministic():
    h1 = url_hash("https://example.com/news/")
    h2 = url_hash("https://example.com/news")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_url_hash_differs_for_different_urls():
    assert url_hash("https://a.com/1") != url_hash("https://a.com/2")


# ── is_seen ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_is_seen_returns_false_for_new_url():
    item = FetchedItem(guid="g1", url="https://example.com/never-seen", title="T", summary=None, published_at=None)
    assert is_seen(item) is False


@pytest.mark.django_db
def test_is_seen_returns_true_for_existing_hash(target_site):
    from newsroom.models import Article, Source
    from newsroom.dedup import url_hash as make_hash

    source = Source.objects.create(name="S", url="https://feed.example.com", target_site=target_site)
    target_url = "https://example.com/known-article"
    Article.objects.create(
        source=source, guid="g1", source_url=target_url,
        url_hash=make_hash(target_url), original_title="Known",
        status="fetched",
    )

    item = FetchedItem(guid="g1", url=target_url, title="Known", summary=None, published_at=None)
    assert is_seen(item) is True


@pytest.mark.django_db
def test_is_seen_matches_despite_utm(target_site):
    from newsroom.models import Article, Source
    from newsroom.dedup import url_hash as make_hash

    source = Source.objects.create(name="S", url="https://feed.example.com", target_site=target_site)
    clean_url = "https://example.com/article"
    Article.objects.create(
        source=source, guid="g1", source_url=clean_url,
        url_hash=make_hash(clean_url), original_title="A",
        status="fetched",
    )

    utm_item = FetchedItem(
        guid="g1",
        url=f"{clean_url}?utm_source=newsletter&utm_medium=email",
        title="A", summary=None, published_at=None,
    )
    assert is_seen(utm_item) is True
