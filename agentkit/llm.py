"""Tool-calling chat through any OpenAI-compatible API, normalised to a small dict."""

from __future__ import annotations

import re
from typing import Protocol

from agentkit.config import Settings


class LLMError(RuntimeError):
    pass


class ChatModel(Protocol):
    model: str

    def chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        """Return {"content": str | None, "tool_calls": [{"id", "name", "arguments"}], "usage": {...}}."""


_SOURCE_MARKER = re.compile(r"\s?【[^】]{0,40}】")
_PLAIN_CHARS = str.maketrans({"\u202f": " ", "\u00a0": " ", "\u2009": " ", "\u2011": "-"})


def tidy_text(text: str | None) -> str | None:
    """gpt-oss models add source markers like 【3†L10-L15】 from their browsing training and put
    narrow no-break spaces inside numbers; neither means anything to a reader here."""
    if not text:
        return text
    return _SOURCE_MARKER.sub("", text.translate(_PLAIN_CHARS))


def provider_options(base_url: str, reasoning_effort: str) -> dict:
    """Extra request options. gpt-oss models reason before answering: keep that short, and on Groq
    leave the reasoning text out of the response (it still counts toward the output tokens)."""
    options: dict = {}
    if reasoning_effort:
        options["reasoning_effort"] = reasoning_effort
    if "groq.com" in base_url:
        options["extra_body"] = {"include_reasoning": False}
    return options


class OpenAICompatible:
    def __init__(self, settings: Settings):
        from openai import OpenAI

        self.model = settings.llm_model
        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_s,
            max_retries=settings.llm_max_retries,
        )
        self._options = provider_options(settings.llm_base_url, settings.llm_reasoning_effort)

    def chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        kwargs = {"model": self.model, "messages": messages, "temperature": 0.2, "max_tokens": 2500, **self._options}
        if tools:
            kwargs.update(tools=tools, tool_choice="auto")
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        msg = response.choices[0].message
        usage = response.usage
        return {
            "content": tidy_text(msg.content),
            "tool_calls": [
                {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments or "{}"}
                for tc in (msg.tool_calls or [])
            ],
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            },
        }
