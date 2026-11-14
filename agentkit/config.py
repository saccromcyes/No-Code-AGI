"""Runtime configuration from environment variables (or .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Any OpenAI-compatible endpoint that supports tool calling (Groq by default).
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    llm_timeout_s: float = 45.0

    database_url: str = f"sqlite:///{ROOT / '.data' / 'agents.db'}"

    # Guard rails for every run
    max_steps: int = 6  # model turns before the agent must answer
    max_tool_calls: int = 12
    tool_timeout_s: float = 10.0
    tool_result_chars: int = 3500
    max_input_chars: int = 2000
    max_notes_chars: int = 20000
    max_agents_per_session: int = 10

    # Public demo limits
    runs_per_10min: int = 20
    run_history: int = 50

    wikipedia_api: str = "https://en.wikipedia.org/w/api.php"
    user_agent: str = "no-code-agent-builder/2.0 (https://github.com/saccromcyes/No-Code-AGI)"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
