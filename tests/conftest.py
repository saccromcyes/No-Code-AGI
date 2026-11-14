from __future__ import annotations

import json

import pytest

from agentkit.config import Settings
from agentkit.llm import LLMError


class ScriptedModel:
    """Plays back a fixed list of model replies. Each item is either a final answer string or a list of
    (tool_name, args) calls. Records the messages it was sent."""

    model = "scripted"

    def __init__(self, script: list, fail_at: int | None = None):
        self.script = list(script)
        self.fail_at = fail_at
        self.calls: list[dict] = []

    def chat(self, messages, tools):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": [t["function"]["name"] for t in tools or []]})
        if self.fail_at is not None and len(self.calls) - 1 == self.fail_at:
            raise LLMError("503 upstream unavailable")
        step = self.script.pop(0) if self.script else "Done."
        usage = {"prompt_tokens": 100, "completion_tokens": 20}
        if isinstance(step, str):
            return {"content": step, "tool_calls": [], "usage": usage}
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": f"call_{len(self.calls)}_{i}",
                    "name": name,
                    "arguments": args if isinstance(args, str) else json.dumps(args),
                }
                for i, (name, args) in enumerate(step)
            ],
            "usage": usage,
        }


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(_env_file=None, llm_api_key="", database_url=f"sqlite:///{tmp_path / 'a.db'}", runs_per_10min=1000)
