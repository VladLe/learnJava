from unittest.mock import MagicMock, patch

import pytest

from newsroom.models import Article, Publication, RewrittenContent, Source, WordPressCategory
from newsroom.publish.base import PublishError, PublishOutcome
from newsroom import pipeline


def _make_rewritten_article(source, n=1):
    article = Article.objects.create(
        source=source,
        guid=f"guid-{n}",
        source_url=f"https://example.com/article-{n}",
        url_hash=f"hash{n:064d}",
        original_title=f"Article {n}",
        full_text="Full text.",
        status=Article.Status.REWRITTEN,
    )
    RewrittenContent.objects.create(
        article=article,
        title=f"New Title {n}",
        body_html="<p>Body.</p>",
        excerpt="Excerpt.",
        seo_title="SEO",
        seo_description="SEO desc.",
        tags=["a"],
        provider="anthropic",
        model="claude-opus-4-8",
    )
    return article


@pytest.mark.django_db
def test_publish_articles_creates_publication(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    article = _make_rewritten_article(source)

    with patch("newsroom.pipeline._publisher.publish") as mock_publish:
        mock_publish.return_value = PublishOutcome(wp_post_id=99, wp_url="https://wp.example.com/?p=99")
        published, failed = pipeline.publish_articles(source)

    assert published == 1
    assert failed == 0
    article.refresh_from_db()
    assert article.status == Article.Status.PUBLISHED

    pub = Publication.objects.get(article=article, target_site=target_site)
    assert pub.status == Publication.Status.PUBLISHED
    assert pub.wp_post_id == 99
    assert pub.published_at is not None


@pytest.mark.django_db
def test_publish_articles_uses_category_and_status(target_site):
    category = WordPressCategory.objects.create(
        site=target_site, wp_category_id=3, name="Tech", slug="tech"
    )
    source = Source.objects.create(
        name="S", url="https://f.example.com", target_site=target_site,
        target_category=category, post_status="publish",
    )
    _make_rewritten_article(source)

    with patch("newsroom.pipeline._publisher.publish") as mock_publish:
        mock_publish.return_value = PublishOutcome(wp_post_id=1, wp_url="https://wp.example.com/?p=1")
        pipeline.publish_articles(source)

    _, kwargs = mock_publish.call_args
    assert kwargs["category"] == category
    assert kwargs["status"] == "publish"


@pytest.mark.django_db
def test_publish_articles_falls_back_to_site_default_status(target_site):
    # site default_status is "draft" by default; source has no post_status
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    _make_rewritten_article(source)

    with patch("newsroom.pipeline._publisher.publish") as mock_publish:
        mock_publish.return_value = PublishOutcome(wp_post_id=1, wp_url="https://wp.example.com/?p=1")
        pipeline.publish_articles(source)

    _, kwargs = mock_publish.call_args
    assert kwargs["status"] == "draft"


@pytest.mark.django_db
def test_publish_articles_handles_error(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    article = _make_rewritten_article(source)

    with patch("newsroom.pipeline._publisher.publish", side_effect=PublishError("500 error")):
        published, failed = pipeline.publish_articles(source)

    assert published == 0
    assert failed == 1
    article.refresh_from_db()
    assert article.status == Article.Status.FAILED
    assert "500 error" in article.error

    pub = Publication.objects.get(article=article, target_site=target_site)
    assert pub.status == Publication.Status.FAILED
    assert "500 error" in pub.error


@pytest.mark.django_db
def test_publish_articles_retry_updates_existing_publication(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    article = _make_rewritten_article(source)

    # First attempt fails
    with patch("newsroom.pipeline._publisher.publish", side_effect=PublishError("timeout")):
        pipeline.publish_articles(source)

    # Reset to rewritten (simulating a retry) and succeed
    Article.objects.filter(pk=article.pk).update(status=Article.Status.REWRITTEN)
    with patch("newsroom.pipeline._publisher.publish") as mock_publish:
        mock_publish.return_value = PublishOutcome(wp_post_id=7, wp_url="https://wp.example.com/?p=7")
        pipeline.publish_articles(source)

    # Still only one Publication row (unique constraint), now successful
    assert Publication.objects.filter(article=article, target_site=target_site).count() == 1
    pub = Publication.objects.get(article=article, target_site=target_site)
    assert pub.status == Publication.Status.PUBLISHED
    assert pub.wp_post_id == 7


@pytest.mark.django_db
def test_publish_articles_skips_non_rewritten(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    Article.objects.create(
        source=source, guid="g1", source_url="https://example.com/done",
        url_hash="a" * 64, original_title="Done",
        status=Article.Status.PUBLISHED,
    )

    with patch("newsroom.pipeline._publisher.publish") as mock_publish:
        published, failed = pipeline.publish_articles(source)

    mock_publish.assert_not_called()
    assert published == 0
    assert failed == 0
