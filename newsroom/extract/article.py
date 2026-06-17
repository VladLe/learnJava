import logging

import httpx
import trafilatura
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; NewsRewriter/1.0; +https://example.com/bot)"
)


class ExtractionError(Exception):
    pass


def extract_text(url: str) -> str:
    """Download a page with httpx and extract its main article text.

    Download and parsing are decoupled: we control the HTTP client (timeout,
    redirects, user-agent) and hand the HTML to trafilatura only for parsing.
    Raises ExtractionError if download or extraction fails.
    """
    user_agent = getattr(settings, "EXTRACT_USER_AGENT", DEFAULT_USER_AGENT)
    try:
        resp = httpx.get(
            url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )
        resp.raise_for_status()
    except Exception as exc:
        raise ExtractionError(f"Could not download page {url}: {exc}") from exc

    text = trafilatura.extract(resp.text, include_comments=False, include_tables=True)
    if not text:
        raise ExtractionError(f"No text could be extracted from: {url}")

    return text
