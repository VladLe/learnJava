import logging

import anthropic
from django.conf import settings

from .base import (
    REWRITE_TOOL_NAME,
    REWRITE_TOOL_SCHEMA,
    RewriteError,
    RewriteRequest,
    RewriteResult,
    RewriteService,
    build_prompts,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-8"


class AnthropicRewriter(RewriteService):
    def __init__(self, model: str | None = None):
        self._model = model or getattr(settings, "ANTHROPIC_MODEL", DEFAULT_MODEL)
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def rewrite(self, req: RewriteRequest) -> RewriteResult:
        system_prompt, user_prompt = build_prompts(req)
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[{
                    "name": REWRITE_TOOL_NAME,
                    "description": "Возвращает переписанную статью в структурированном виде",
                    "input_schema": REWRITE_TOOL_SCHEMA,
                }],
                tool_choice={"type": "tool", "name": REWRITE_TOOL_NAME},
            )
        except Exception as exc:
            raise RewriteError(f"Anthropic API error: {exc}") from exc

        data = next(
            (block.input for block in response.content if block.type == "tool_use"),
            None,
        )
        if data is None:
            raise RewriteError("Anthropic response contained no tool_use block")

        logger.info(
            "Anthropic rewrite done: model=%s tokens=%d+%d",
            self._model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return RewriteResult(
            title=data["title"],
            body_html=data["body_html"],
            excerpt=data["excerpt"],
            seo_title=data["seo_title"],
            seo_description=data["seo_description"],
            tags=data["tags"],
            provider="anthropic",
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
