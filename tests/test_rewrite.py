import json
from unittest.mock import MagicMock, patch

import pytest

from newsroom.rewrite.base import (
    RewriteError,
    RewriteRequest,
    RewriteResult,
    build_prompts,
)


def _make_request(**kwargs):
    defaults = dict(
        title="Заголовок статьи",
        body="Текст оригинала.",
        source_url="https://example.com/article",
    )
    defaults.update(kwargs)
    return RewriteRequest(**defaults)


def _expected_result(**kwargs):
    defaults = dict(
        title="Новый заголовок",
        body_html="<p>Переписанный текст.</p>",
        excerpt="Краткое описание.",
        seo_title="SEO заголовок",
        seo_description="SEO описание для поисковиков.",
        tags=["тег1", "тег2"],
        provider="anthropic",
        model="claude-opus-4-8",
        input_tokens=100,
        output_tokens=200,
    )
    defaults.update(kwargs)
    return defaults


# ── build_prompts ─────────────────────────────────────────────────────────────

def test_build_prompts_contains_title_and_body():
    req = _make_request()
    system, user = build_prompts(req)
    assert req.title in user
    assert req.body in user


def test_build_prompts_contains_source_url_attribution():
    req = _make_request(source_url="https://example.com/news/1")
    system, _ = build_prompts(req)
    assert "https://example.com/news/1" in system


def test_build_prompts_tone_labels():
    req = _make_request(tone="analytical")
    _, user = build_prompts(req)
    assert "аналитический" in user


def test_build_prompts_length_labels():
    req = _make_request(target_length="long")
    _, user = build_prompts(req)
    assert "~1000" in user


# ── AnthropicRewriter ─────────────────────────────────────────────────────────

def _mock_anthropic_response(data: dict, input_tokens=100, output_tokens=200):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = data

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    response = MagicMock()
    response.content = [tool_block]
    response.usage = usage
    return response


def test_anthropic_rewriter_returns_result():
    from newsroom.rewrite.anthropic import AnthropicRewriter

    data = _expected_result()
    mock_response = _mock_anthropic_response(data)

    with patch("newsroom.rewrite.anthropic.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        result = AnthropicRewriter().rewrite(_make_request())

    assert isinstance(result, RewriteResult)
    assert result.title == data["title"]
    assert result.body_html == data["body_html"]
    assert result.provider == "anthropic"
    assert result.input_tokens == 100
    assert result.output_tokens == 200


def test_anthropic_rewriter_raises_on_api_error():
    from newsroom.rewrite.anthropic import AnthropicRewriter

    with patch("newsroom.rewrite.anthropic.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = RuntimeError("connection error")

        with pytest.raises(RewriteError, match="Anthropic API error"):
            AnthropicRewriter().rewrite(_make_request())


def test_anthropic_rewriter_raises_when_no_tool_block():
    from newsroom.rewrite.anthropic import AnthropicRewriter

    text_block = MagicMock()
    text_block.type = "text"
    response = MagicMock()
    response.content = [text_block]

    with patch("newsroom.rewrite.anthropic.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = response

        with pytest.raises(RewriteError, match="no tool_use block"):
            AnthropicRewriter().rewrite(_make_request())


# ── OpenAIRewriter ────────────────────────────────────────────────────────────

def _mock_openai_response(data: dict, prompt_tokens=150, completion_tokens=250):
    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps(data)

    message = MagicMock()
    message.tool_calls = [tool_call]

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


def test_openai_rewriter_returns_result():
    from newsroom.rewrite.openai import OpenAIRewriter

    data = _expected_result(provider="openai", model="gpt-4o")
    mock_response = _mock_openai_response(data)

    with patch("newsroom.rewrite.openai.openai.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        result = OpenAIRewriter().rewrite(_make_request())

    assert isinstance(result, RewriteResult)
    assert result.title == data["title"]
    assert result.provider == "openai"
    assert result.input_tokens == 150
    assert result.output_tokens == 250


def test_openai_rewriter_raises_on_api_error():
    from newsroom.rewrite.openai import OpenAIRewriter

    with patch("newsroom.rewrite.openai.openai.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = RuntimeError("rate limit")

        with pytest.raises(RewriteError, match="OpenAI API error"):
            OpenAIRewriter().rewrite(_make_request())


def test_openai_rewriter_raises_when_no_tool_calls():
    from newsroom.rewrite.openai import OpenAIRewriter

    message = MagicMock()
    message.tool_calls = []
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]

    with patch("newsroom.rewrite.openai.openai.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = response

        with pytest.raises(RewriteError, match="no tool calls"):
            OpenAIRewriter().rewrite(_make_request())


# ── factory ───────────────────────────────────────────────────────────────────

def test_factory_returns_anthropic(settings):
    settings.REWRITE_PROVIDER = "anthropic"
    settings.ANTHROPIC_API_KEY = "test-key"

    with patch("newsroom.rewrite.anthropic.anthropic.Anthropic"):
        from newsroom.rewrite.factory import get_rewriter
        from newsroom.rewrite.anthropic import AnthropicRewriter
        assert isinstance(get_rewriter(), AnthropicRewriter)


def test_factory_returns_openai(settings):
    settings.REWRITE_PROVIDER = "openai"
    settings.OPENAI_API_KEY = "test-key"

    with patch("newsroom.rewrite.openai.openai.OpenAI"):
        from newsroom.rewrite.factory import get_rewriter
        from newsroom.rewrite.openai import OpenAIRewriter
        assert isinstance(get_rewriter(), OpenAIRewriter)


def test_factory_raises_on_unknown_provider(settings):
    settings.REWRITE_PROVIDER = "gemini"
    from newsroom.rewrite.factory import get_rewriter
    with pytest.raises(ValueError, match="Unknown rewrite provider"):
        get_rewriter()
