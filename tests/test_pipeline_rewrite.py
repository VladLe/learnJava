from unittest.mock import MagicMock, patch

import pytest

from newsroom.models import Article, RewrittenContent, Source
from newsroom.rewrite.base import RewriteError, RewriteResult
from newsroom import pipeline


def _make_extracted_article(source, n=1):
    return Article.objects.create(
        source=source,
        guid=f"guid-{n}",
        source_url=f"https://example.com/article-{n}",
        url_hash=f"hash{n:064d}",
        original_title=f"Article {n}",
        full_text="Full article text.",
        status=Article.Status.EXTRACTED,
    )


def _fake_result(**kwargs):
    defaults = dict(
        title="New Title",
        body_html="<p>Body.</p>",
        excerpt="Excerpt.",
        seo_title="SEO",
        seo_description="SEO desc.",
        tags=["a", "b"],
        provider="anthropic",
        model="claude-opus-4-8",
        input_tokens=100,
        output_tokens=200,
    )
    defaults.update(kwargs)
    return RewriteResult(**defaults)


@pytest.mark.django_db
def test_rewrite_articles_creates_rewritten_content(target_site, settings):
    settings.REWRITE_PROVIDER = "anthropic"
    settings.ANTHROPIC_API_KEY = "test"
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    article = _make_extracted_article(source)

    with (
        patch("newsroom.rewrite.anthropic.anthropic.Anthropic"),
        patch("newsroom.pipeline.get_rewriter") as mock_factory,
    ):
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite.return_value = _fake_result()
        mock_factory.return_value = mock_rewriter

        rewritten, failed = pipeline.rewrite_articles(source)

    assert rewritten == 1
    assert failed == 0
    article.refresh_from_db()
    assert article.status == Article.Status.REWRITTEN

    rc = RewrittenContent.objects.get(article=article)
    assert rc.title == "New Title"
    assert rc.provider == "anthropic"
    assert rc.input_tokens == 100


@pytest.mark.django_db
def test_rewrite_articles_handles_error(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    article = _make_extracted_article(source)

    with patch("newsroom.pipeline.get_rewriter") as mock_factory:
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite.side_effect = RewriteError("LLM timeout")
        mock_factory.return_value = mock_rewriter

        rewritten, failed = pipeline.rewrite_articles(source)

    assert rewritten == 0
    assert failed == 1
    article.refresh_from_db()
    assert article.status == Article.Status.FAILED
    assert "LLM timeout" in article.error


@pytest.mark.django_db
def test_rewrite_articles_scoped_to_source(target_site):
    s1 = Source.objects.create(name="S1", url="https://f1.example.com", target_site=target_site)
    s2 = Source.objects.create(name="S2", url="https://f2.example.com", target_site=target_site)
    a1 = _make_extracted_article(s1, 1)
    a2 = _make_extracted_article(s2, 2)

    with patch("newsroom.pipeline.get_rewriter") as mock_factory:
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite.return_value = _fake_result()
        mock_factory.return_value = mock_rewriter

        pipeline.rewrite_articles(s1)

    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.status == Article.Status.REWRITTEN
    assert a2.status == Article.Status.EXTRACTED  # untouched


@pytest.mark.django_db
def test_rewrite_articles_skips_non_extracted(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    Article.objects.create(
        source=source, guid="g1", source_url="https://example.com/done",
        url_hash="a" * 64, original_title="Done",
        status=Article.Status.REWRITTEN,
    )

    with patch("newsroom.pipeline.get_rewriter") as mock_factory:
        mock_rewriter = MagicMock()
        mock_factory.return_value = mock_rewriter

        rewritten, failed = pipeline.rewrite_articles(source)

    mock_rewriter.rewrite.assert_not_called()
    assert rewritten == 0
