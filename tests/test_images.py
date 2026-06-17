from unittest.mock import MagicMock, patch

import pytest

from newsroom.images.base import ImageCandidate, ImageError
from newsroom.images.factory import get_image_provider
from newsroom.images.pexels import PexelsImageProvider


# ── PexelsImageProvider ───────────────────────────────────────────────────────

def _pexels_response(photos):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"photos": photos}
    return resp


def test_pexels_requires_api_key(settings):
    settings.PEXELS_API_KEY = ""
    with pytest.raises(ImageError, match="PEXELS_API_KEY"):
        PexelsImageProvider()


def test_pexels_search_returns_candidate(settings):
    settings.PEXELS_API_KEY = "key"
    photo = {
        "src": {"large2x": "https://images.pexels.com/p/1-large2x.jpg",
                "large": "https://images.pexels.com/p/1-large.jpg"},
        "alt": "A laptop on a desk",
        "photographer": "Jane Doe",
        "url": "https://www.pexels.com/photo/1/",
    }
    with patch("newsroom.images.pexels.httpx.get", return_value=_pexels_response([photo])) as mock_get:
        candidate = PexelsImageProvider().search("technology news")

    assert isinstance(candidate, ImageCandidate)
    assert candidate.url == "https://images.pexels.com/p/1-large2x.jpg"
    assert candidate.alt == "A laptop on a desk"
    assert candidate.credit == "Jane Doe"

    # query and auth header are sent
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["query"] == "technology news"
    assert kwargs["headers"]["Authorization"] == "key"


def test_pexels_search_returns_none_when_empty(settings):
    settings.PEXELS_API_KEY = "key"
    with patch("newsroom.images.pexels.httpx.get", return_value=_pexels_response([])):
        assert PexelsImageProvider().search("nothing here") is None


def test_pexels_search_raises_on_http_error(settings):
    settings.PEXELS_API_KEY = "key"
    import httpx
    with patch("newsroom.images.pexels.httpx.get", side_effect=httpx.ConnectError("x")):
        with pytest.raises(ImageError, match="Pexels API error"):
            PexelsImageProvider().search("q")


# ── factory ───────────────────────────────────────────────────────────────────

def test_factory_returns_none_when_disabled(settings):
    settings.IMAGE_PROVIDER = "none"
    assert get_image_provider() is None


def test_factory_returns_pexels(settings):
    settings.IMAGE_PROVIDER = "pexels"
    settings.PEXELS_API_KEY = "key"
    assert isinstance(get_image_provider(), PexelsImageProvider)


def test_factory_raises_on_unknown(settings):
    settings.IMAGE_PROVIDER = "shutterstock"
    with pytest.raises(ValueError, match="Unknown image provider"):
        get_image_provider()
