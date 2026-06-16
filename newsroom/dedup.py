import hashlib
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .models import Article
from .sources.base import FetchedItem

_UTM_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign",
    "utm_term", "utm_content", "utm_id", "utm_source_platform",
})


def normalize_url(url: str) -> str:
    p = urlparse(url)
    qs = parse_qs(p.query, keep_blank_values=False)
    clean = {k: v for k, v in qs.items() if k not in _UTM_PARAMS}
    return urlunparse((
        p.scheme.lower(),
        p.netloc.lower(),
        p.path.rstrip("/") or "/",
        p.params,
        urlencode(sorted(clean.items()), doseq=True),
        "",  # drop fragment
    ))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


def is_seen(item: FetchedItem) -> bool:
    h = url_hash(item.url)
    return Article.objects.filter(url_hash=h).exists()
