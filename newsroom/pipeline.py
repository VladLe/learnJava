import logging

from django.db import IntegrityError
from django.utils import timezone

from .models import Article, Source
from . import dedup
from .extract.article import ExtractionError, extract_text
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
