import logging

import httpx
from django.conf import settings

from .base import ImageCandidate, ImageError, ImageProvider

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.pexels.com/v1/search"


class PexelsImageProvider(ImageProvider):
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or settings.PEXELS_API_KEY
        if not self._api_key:
            raise ImageError("PEXELS_API_KEY is not set")

    def search(self, query: str) -> ImageCandidate | None:
        try:
            resp = httpx.get(
                SEARCH_URL,
                headers={"Authorization": self._api_key},
                params={"query": query, "per_page": 1, "orientation": "landscape"},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise ImageError(f"Pexels API error: {exc}") from exc

        photos = resp.json().get("photos", [])
        if not photos:
            logger.info("Pexels: no images for query %r", query)
            return None

        photo = photos[0]
        src = photo.get("src", {})
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            return None

        return ImageCandidate(
            url=url,
            alt=photo.get("alt") or query,
            credit=photo.get("photographer", ""),
            source_page=photo.get("url", ""),
        )
