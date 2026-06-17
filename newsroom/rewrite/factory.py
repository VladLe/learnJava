from django.conf import settings

from .base import RewriteService


def get_rewriter() -> RewriteService:
    provider = getattr(settings, "REWRITE_PROVIDER", "anthropic")
    if provider == "anthropic":
        from .anthropic import AnthropicRewriter
        return AnthropicRewriter()
    if provider == "openai":
        from .openai import OpenAIRewriter
        return OpenAIRewriter()
    raise ValueError(
        f"Unknown rewrite provider: {provider!r}. "
        "Set REWRITE_PROVIDER to 'anthropic' or 'openai'."
    )
