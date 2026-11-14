"""Tool-calling chat through any OpenAI-compatible API, normalised to a small dict."""

from __future__ import annotations

from typing import Protocol

from agentkit.config import Settings


class LLMError(RuntimeError):
    pass


class ChatModel(Protocol):
    model: str

    def chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        """Return {"content": str | None, "tool_calls": [{"id", "name", "arguments"}], "usage": {...}}."""


class OpenAICompatible:
    def __init__(self, settings: Settings):
        from openai import OpenAI

        self.model = settings.llm_model
        self._client = OpenAI(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key, timeout=settings.llm_timeout_s, max_retries=2
        )

    def chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        kwargs = {"model": self.model, "messages": messages, "temperature": 0.2, "max_tokens": 900}
        if tools:
            kwargs.update(tools=tools, tool_choice="auto", parallel_tool_calls=True)
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise LLMError(str(exc)) from exc
        msg = response.choices[0].message
        usage = response.usage
        return {
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments or "{}"}
                for tc in (msg.tool_calls or [])
            ],
            "usage": {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            },
        }
