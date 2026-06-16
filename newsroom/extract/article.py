import logging

import trafilatura

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    pass


def extract_text(url: str) -> str:
    """Download a page and extract its main article text.

    Raises ExtractionError if download or extraction fails.
    """
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ExtractionError(f"Could not download page: {url}")

    text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
    if not text:
        raise ExtractionError(f"No text could be extracted from: {url}")

    return text
