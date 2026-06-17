from abc import ABC, abstractmethod
from dataclasses import dataclass


class RewriteError(Exception):
    pass


@dataclass
class RewriteRequest:
    title: str
    body: str
    source_url: str
    language: str = "ru"
    tone: str = "neutral"          # neutral | analytical | conversational
    target_length: str = "medium"  # short | medium | long


@dataclass
class RewriteResult:
    title: str
    body_html: str
    excerpt: str
    seo_title: str
    seo_description: str
    tags: list[str]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class RewriteService(ABC):
    @abstractmethod
    def rewrite(self, req: RewriteRequest) -> RewriteResult: ...


# ── Shared tool schema (used for function/tool calling in both providers) ─────

REWRITE_TOOL_NAME = "rewrite_article"

REWRITE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Новый заголовок статьи",
        },
        "body_html": {
            "type": "string",
            "description": "Тело поста в HTML для WordPress (p, h2, h3, ul, ol, strong, em)",
        },
        "excerpt": {
            "type": "string",
            "description": "Краткое описание (2–3 предложения)",
        },
        "seo_title": {
            "type": "string",
            "description": "SEO-заголовок (до 60 символов)",
        },
        "seo_description": {
            "type": "string",
            "description": "SEO-описание (120–160 символов)",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ключевые слова/фразы (3–7 тегов)",
        },
    },
    "required": ["title", "body_html", "excerpt", "seo_title", "seo_description", "tags"],
}

_TONE_LABELS = {
    "neutral": "нейтральный",
    "analytical": "аналитический",
    "conversational": "разговорный",
}

_LENGTH_WORDS = {
    "short": "~300",
    "medium": "~600",
    "long": "~1000",
}


def build_prompts(req: RewriteRequest) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the given rewrite request."""
    tone_label = _TONE_LABELS.get(req.tone, req.tone)
    length_words = _LENGTH_WORDS.get(req.target_length, req.target_length)

    system = (
        "Ты профессиональный редактор новостного сайта. "
        "Переписываешь статьи своими словами, сохраняя все факты и ключевые детали. "
        "Не выдумываешь информацию, которой нет в оригинале. "
        "Тело поста оформляешь в валидный HTML для WordPress "
        "(используй теги p, h2, h3, ul, ol, strong, em). "
        "В конце тела всегда добавляешь абзац с атрибуцией:\n"
        f'<p>По материалам: <a href="{req.source_url}">оригинальной статьи</a>.</p>'
    )

    user = (
        f"Перепиши статью.\n"
        f"Тон: {tone_label}\n"
        f"Длина: {length_words} слов\n"
        f"Язык вывода: {req.language}\n\n"
        f"Оригинальный заголовок: {req.title}\n\n"
        f"Текст статьи:\n{req.body}"
    )

    return system, user
