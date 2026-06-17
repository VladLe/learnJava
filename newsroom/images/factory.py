from django.conf import settings

from .base import ImageProvider


def get_image_provider() -> ImageProvider | None:
    """Return the configured image provider, or None if disabled.

    Controlled by IMAGE_PROVIDER: "none" (default) disables featured images.
    """
    provider = getattr(settings, "IMAGE_PROVIDER", "none")
    if provider in ("", "none"):
        return None
    if provider == "pexels":
        from .pexels import PexelsImageProvider
        return PexelsImageProvider()
    raise ValueError(
        f"Unknown image provider: {provider!r}. "
        "Set IMAGE_PROVIDER to 'none' or 'pexels'."
    )
