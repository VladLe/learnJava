import logging

from django.db import IntegrityError
from django.utils import timezone

from .models import Article, Publication, RewrittenContent, Source
from . import dedup
from .extract.article import extract_text
from .publish.wordpress import WordPressPublisher
from .rewrite.base import RewriteRequest
from .rewrite.factory import get_rewriter
from .sources.rss import RssFetcher

logger = logging.getLogger(__name__)

_fetcher = RssFetcher()


def fetch_and_store(source: Source) -> tuple[int, int]:
    """Fetch RSS feed, skip duplicates, save new articles as 'fetched'.

    Returns (saved, skipped).
    """
    items = _fetcher.fetch(source)
    saved = skipped = 0

    for item in items:
        if dedup.is_seen(item):
            skipped += 1
            continue
        try:
            Article.objects.create(
                source=source,
                guid=item.guid,
                source_url=item.url,
                url_hash=dedup.url_hash(item.url),
                original_title=item.title,
                original_summary=item.summary or "",
                published_at=item.published_at,
                status=Article.Status.FETCHED,
            )
            saved += 1
        except IntegrityError:
            # Race: another worker saved the same URL between is_seen and create
            skipped += 1

    source.last_fetched_at = timezone.now()
    source.save(update_fields=["last_fetched_at"])
    logger.info("Source '%s': saved=%d skipped=%d", source.name, saved, skipped)
    return saved, skipped


def extract_articles(source: Source | None = None) -> tuple[int, int]:
    """Extract full text for all articles in 'fetched' status.

    Optionally scoped to a single source. Returns (extracted, failed).
    """
    qs = Article.objects.filter(status=Article.Status.FETCHED)
    if source is not None:
        qs = qs.filter(source=source)

    extracted = failed = 0
    for article in qs:
        try:
            text = extract_text(article.source_url)
            Article.objects.filter(pk=article.pk).update(
                full_text=text,
                status=Article.Status.EXTRACTED,
                error="",
            )
            extracted += 1
            logger.info("Extracted: %s", article.original_title)
        except Exception as exc:
            Article.objects.filter(pk=article.pk).update(
                status=Article.Status.FAILED,
                error=str(exc),
            )
            failed += 1
            logger.warning("Extraction failed for %s: %s", article.source_url, exc)

    return extracted, failed


def rewrite_articles(source: Source | None = None) -> tuple[int, int]:
    """Rewrite all articles in 'extracted' status via the configured LLM provider.

    Optionally scoped to a single source. Returns (rewritten, failed).
    """
    qs = Article.objects.filter(status=Article.Status.EXTRACTED).select_related("source")
    if source is not None:
        qs = qs.filter(source=source)

    rewriter = get_rewriter()
    rewritten = failed = 0

    for article in qs:
        try:
            req = RewriteRequest(
                title=article.original_title,
                body=article.full_text,
                source_url=article.source_url,
                tone=article.source.tone,
                target_length=article.source.target_length,
            )
            result = rewriter.rewrite(req)

            RewrittenContent.objects.create(
                article=article,
                title=result.title,
                body_html=result.body_html,
                excerpt=result.excerpt,
                seo_title=result.seo_title,
                seo_description=result.seo_description,
                tags=result.tags,
                provider=result.provider,
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
            Article.objects.filter(pk=article.pk).update(
                status=Article.Status.REWRITTEN, error=""
            )
            rewritten += 1
            logger.info("Rewritten: %s", article.original_title)
        except Exception as exc:
            Article.objects.filter(pk=article.pk).update(
                status=Article.Status.FAILED, error=str(exc)
            )
            failed += 1
            logger.warning("Rewrite failed for article %d: %s", article.pk, exc)

    return rewritten, failed


_publisher = WordPressPublisher()


def publish_articles(source: Source | None = None) -> tuple[int, int]:
    """Publish all articles in 'rewritten' status to their target WordPress site.

    Optionally scoped to a single source. Returns (published, failed).
    """
    qs = (
        Article.objects.filter(status=Article.Status.REWRITTEN)
        .select_related("source", "source__target_site", "source__target_category", "rewritten")
    )
    if source is not None:
        qs = qs.filter(source=source)

    published = failed = 0

    for article in qs:
        src = article.source
        site = src.target_site
        status = src.post_status or site.default_status

        try:
            outcome = _publisher.publish(
                site=site,
                category=src.target_category,
                content=article.rewritten,
                source_url=article.source_url,
                status=status,
            )
            Publication.objects.update_or_create(
                article=article,
                target_site=site,
                defaults={
                    "wp_post_id": outcome.wp_post_id,
                    "wp_url": outcome.wp_url,
                    "status": Publication.Status.PUBLISHED,
                    "error": "",
                    "published_at": timezone.now(),
                },
            )
            Article.objects.filter(pk=article.pk).update(
                status=Article.Status.PUBLISHED, error=""
            )
            published += 1
            logger.info("Published: %s → %s", article.original_title, outcome.wp_url)
        except Exception as exc:
            Publication.objects.update_or_create(
                article=article,
                target_site=site,
                defaults={
                    "status": Publication.Status.FAILED,
                    "error": str(exc),
                },
            )
            Article.objects.filter(pk=article.pk).update(
                status=Article.Status.FAILED, error=str(exc)
            )
            failed += 1
            logger.warning("Publish failed for article %d: %s", article.pk, exc)

    return published, failed


def run_source(source: Source) -> dict:
    """Run the full pipeline end-to-end for a single source.

    Each stage selects articles by status, so stages are idempotent and a
    rerun continues where the previous run stopped. Returns per-stage counts.
    """
    logger.info("Running full pipeline for source '%s'", source.name)

    saved, skipped = fetch_and_store(source)
    extracted, extract_failed = extract_articles(source)
    rewritten, rewrite_failed = rewrite_articles(source)
    published, publish_failed = publish_articles(source)

    result = {
        "fetched": saved,
        "skipped": skipped,
        "extracted": extracted,
        "rewritten": rewritten,
        "published": published,
        "failed": extract_failed + rewrite_failed + publish_failed,
    }
    logger.info("Source '%s' pipeline result: %s", source.name, result)
    return result
