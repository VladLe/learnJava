import logging

from django.db import IntegrityError
from django.utils import timezone

from .models import Article, Source
from . import dedup
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
