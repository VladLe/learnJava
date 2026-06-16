import json
import logging

import openai
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

DEFAULT_MODEL = "gpt-4o"


class OpenAIRewriter(RewriteService):
    def __init__(self, model: str | None = None):
        self._model = model or getattr(settings, "OPENAI_MODEL", DEFAULT_MODEL)
        self._client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    def rewrite(self, req: RewriteRequest) -> RewriteResult:
        system_prompt, user_prompt = build_prompts(req)
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=[{
                    "type": "function",
                    "function": {
                        "name": REWRITE_TOOL_NAME,
                        "description": "Возвращает переписанную статью в структурированном виде",
                        "parameters": REWRITE_TOOL_SCHEMA,
                    },
                }],
                tool_choice={"type": "function", "function": {"name": REWRITE_TOOL_NAME}},
            )
        except Exception as exc:
            raise RewriteError(f"OpenAI API error: {exc}") from exc

        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            raise RewriteError("OpenAI response contained no tool calls")

        data = json.loads(tool_calls[0].function.arguments)
        usage = response.usage

        logger.info(
            "OpenAI rewrite done: model=%s tokens=%d+%d",
            self._model,
            usage.prompt_tokens,
            usage.completion_tokens,
        )
        return RewriteResult(
            title=data["title"],
            body_html=data["body_html"],
            excerpt=data["excerpt"],
            seo_title=data["seo_title"],
            seo_description=data["seo_description"],
            tags=data["tags"],
            provider="openai",
            model=self._model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )
