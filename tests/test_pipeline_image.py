from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from newsroom.images.base import ImageCandidate
from newsroom.models import Article, RewrittenContent, Source
from newsroom.publish.base import PublishOutcome
from newsroom import pipeline


def _make_rewritten_article(source, tags):
    article = Article.objects.create(
        source=source, guid="g1", source_url="https://example.com/1",
        url_hash="a" * 64, original_title="Orig", full_text="text",
        status=Article.Status.REWRITTEN,
    )
    RewrittenContent.objects.create(
        article=article, title="New Title", body_html="<p>B</p>", excerpt="E",
        seo_title="s", seo_description="d", tags=tags,
        provider="anthropic", model="claude-opus-4-8",
    )
    return article


# ── _image_query ──────────────────────────────────────────────────────────────

def test_image_query_prefers_tags():
    content = SimpleNamespace(tags=["politics", "economy", "extra"], title="Long title")
    assert pipeline._image_query(content) == "politics economy"


def test_image_query_falls_back_to_title():
    content = SimpleNamespace(tags=[], title="Breaking news today")
    assert pipeline._image_query(content) == "Breaking news today"


# ── _select_image ─────────────────────────────────────────────────────────────

def test_select_image_returns_none_without_provider():
    content = SimpleNamespace(tags=["x"], title="t")
    assert pipeline._select_image(None, content) is None


def test_select_image_swallows_errors():
    provider = MagicMock()
    provider.search.side_effect = RuntimeError("boom")
    content = SimpleNamespace(tags=["x"], title="t")
    assert pipeline._select_image(provider, content) is None


# ── publish_articles integration ──────────────────────────────────────────────

@pytest.mark.django_db
def test_publish_passes_image_when_enabled(target_site):
    source = Source.objects.create(
        name="S", url="https://f.example.com", target_site=target_site,
        add_featured_image=True,
    )
    _make_rewritten_article(source, ["tech"])

    candidate = ImageCandidate(url="https://img/1.jpg", alt="a", credit="c", source_page="p")
    provider = MagicMock()
    provider.search.return_value = candidate

    with (
        patch("newsroom.pipeline.get_image_provider", return_value=provider),
        patch("newsroom.pipeline._publisher.publish") as mock_publish,
    ):
        mock_publish.return_value = PublishOutcome(wp_post_id=1, wp_url="https://wp/?p=1")
        pipeline.publish_articles(source)

    _, kwargs = mock_publish.call_args
    assert kwargs["image"] == candidate


@pytest.mark.django_db
def test_publish_skips_image_when_disabled_on_source(target_site):
    source = Source.objects.create(
        name="S", url="https://f.example.com", target_site=target_site,
        add_featured_image=False,
    )
    _make_rewritten_article(source, ["tech"])

    provider = MagicMock()

    with (
        patch("newsroom.pipeline.get_image_provider", return_value=provider),
        patch("newsroom.pipeline._publisher.publish") as mock_publish,
    ):
        mock_publish.return_value = PublishOutcome(wp_post_id=1, wp_url="https://wp/?p=1")
        pipeline.publish_articles(source)

    provider.search.assert_not_called()
    _, kwargs = mock_publish.call_args
    assert kwargs["image"] is None


@pytest.mark.django_db
def test_publish_image_none_when_no_provider(target_site):
    source = Source.objects.create(
        name="S", url="https://f.example.com", target_site=target_site,
        add_featured_image=True,
    )
    _make_rewritten_article(source, ["tech"])

    with (
        patch("newsroom.pipeline.get_image_provider", return_value=None),
        patch("newsroom.pipeline._publisher.publish") as mock_publish,
    ):
        mock_publish.return_value = PublishOutcome(wp_post_id=1, wp_url="https://wp/?p=1")
        pipeline.publish_articles(source)

    _, kwargs = mock_publish.call_args
    assert kwargs["image"] is None
