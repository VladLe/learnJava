import logging
from datetime import datetime, timezone

import feedparser

from .base import FetchedItem, SourceFetcher

logger = logging.getLogger(__name__)


class RssFetcher(SourceFetcher):
    def fetch(self, source) -> list[FetchedItem]:
        logger.debug("Fetching RSS: %s", source.url)
        feed = feedparser.parse(source.url)
        if feed.bozo:
            logger.warning("Bozo feed %s: %s", source.url, feed.bozo_exception)

        items: list[FetchedItem] = []
        for entry in feed.entries:
            url = (entry.get("link") or "").strip()
            if not url:
                continue
            guid = (entry.get("id") or "").strip() or url
            title = (entry.get("title") or "").strip()
            summary = entry.get("summary") or entry.get("description") or None
            items.append(FetchedItem(
                guid=guid,
                url=url,
                title=title,
                summary=summary,
                published_at=_parse_date(entry),
            ))
        return items


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    return None
