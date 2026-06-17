from unittest.mock import MagicMock, patch

import pytest

from newsroom.models import Article, RewrittenContent, Source
from newsroom.rewrite.base import RewriteResult
from newsroom import pipeline


def _extracted_article(source, n=1):
    return Article.objects.create(
        source=source, guid=f"g{n}", source_url=f"https://example.com/{n}",
        url_hash=f"h{n:064d}", original_title=f"A{n}", full_text="text",
        status=Article.Status.EXTRACTED,
    )


def _fake_result():
    return RewriteResult(
        title="T", body_html="<p>B</p>", excerpt="E", seo_title="s",
        seo_description="d", tags=["a"], provider="anthropic",
        model="claude-opus-4-8", input_tokens=10, output_tokens=20,
    )


def _patch_rewriter():
    mock_rewriter = MagicMock()
    mock_rewriter.rewrite.return_value = _fake_result()
    return patch("newsroom.pipeline.get_rewriter", return_value=mock_rewriter)


# ── rewrite routing ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_rewrite_goes_to_pending_when_moderation_required(target_site):
    source = Source.objects.create(
        name="S", url="https://f.example.com", target_site=target_site,
        require_moderation=True,
    )
    article = _extracted_article(source)

    with _patch_rewriter():
        pipeline.rewrite_articles(source)

    article.refresh_from_db()
    assert article.status == Article.Status.PENDING
    assert RewrittenContent.objects.filter(article=article).exists()


@pytest.mark.django_db
def test_rewrite_goes_to_rewritten_without_moderation(target_site):
    source = Source.objects.create(
        name="S", url="https://f.example.com", target_site=target_site,
        require_moderation=False,
    )
    article = _extracted_article(source)

    with _patch_rewriter():
        pipeline.rewrite_articles(source)

    article.refresh_from_db()
    assert article.status == Article.Status.REWRITTEN


# ── publish does not pick up pending articles ─────────────────────────────────

@pytest.mark.django_db
def test_publish_skips_pending_articles(target_site):
    source = Source.objects.create(
        name="S", url="https://f.example.com", target_site=target_site,
        require_moderation=True,
    )
    article = _extracted_article(source)
    RewrittenContent.objects.create(
        article=article, title="T", body_html="<p>B</p>", excerpt="E",
        seo_title="s", seo_description="d", tags=[], provider="anthropic",
        model="claude-opus-4-8",
    )
    Article.objects.filter(pk=article.pk).update(status=Article.Status.PENDING)

    with patch("newsroom.pipeline._publisher.publish") as mock_publish:
        published, failed = pipeline.publish_articles(source)

    mock_publish.assert_not_called()
    assert published == 0


# ── admin approve / reject ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_approve_action_moves_pending_to_rewritten(admin_client, target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    article = _extracted_article(source)
    Article.objects.filter(pk=article.pk).update(status=Article.Status.PENDING)

    admin_client.post(
        "/admin/newsroom/article/",
        {"action": "action_approve", "_selected_action": [article.pk]},
    )

    article.refresh_from_db()
    assert article.status == Article.Status.REWRITTEN


@pytest.mark.django_db
def test_reject_action_moves_pending_to_rejected(admin_client, target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    article = _extracted_article(source)
    Article.objects.filter(pk=article.pk).update(status=Article.Status.PENDING)

    admin_client.post(
        "/admin/newsroom/article/",
        {"action": "action_reject", "_selected_action": [article.pk]},
    )

    article.refresh_from_db()
    assert article.status == Article.Status.REJECTED


@pytest.mark.django_db
def test_approve_only_affects_pending(admin_client, target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    published = _extracted_article(source, 1)
    Article.objects.filter(pk=published.pk).update(status=Article.Status.PUBLISHED)

    admin_client.post(
        "/admin/newsroom/article/",
        {"action": "action_approve", "_selected_action": [published.pk]},
    )

    published.refresh_from_db()
    assert published.status == Article.Status.PUBLISHED  # unchanged


# ── end-to-end: moderation holds, then approval publishes ─────────────────────

@pytest.mark.django_db
def test_run_source_holds_for_moderation_then_publishes_after_approval(target_site):
    source = Source.objects.create(
        name="S", url="https://f.example.com", target_site=target_site,
        require_moderation=True, add_featured_image=False,
    )
    article = _extracted_article(source)

    from newsroom.publish.base import PublishOutcome

    # First run: fetch finds nothing new, but extracted→rewrite→pending; publish holds.
    with (
        patch("newsroom.pipeline.fetch_and_store", return_value=(0, 0)),
        _patch_rewriter(),
        patch("newsroom.pipeline.get_image_provider", return_value=None),
        patch("newsroom.pipeline._publisher.publish") as mock_publish,
    ):
        pipeline.run_source(source)

    article.refresh_from_db()
    assert article.status == Article.Status.PENDING
    mock_publish.assert_not_called()

    # Human approves.
    Article.objects.filter(pk=article.pk).update(status=Article.Status.REWRITTEN)

    # Second run publishes the approved article.
    with (
        patch("newsroom.pipeline.fetch_and_store", return_value=(0, 0)),
        _patch_rewriter(),
        patch("newsroom.pipeline.get_image_provider", return_value=None),
        patch("newsroom.pipeline._publisher.publish") as mock_publish,
    ):
        mock_publish.return_value = PublishOutcome(wp_post_id=5, wp_url="https://wp/?p=5")
        pipeline.run_source(source)

    article.refresh_from_db()
    assert article.status == Article.Status.PUBLISHED
    mock_publish.assert_called_once()
