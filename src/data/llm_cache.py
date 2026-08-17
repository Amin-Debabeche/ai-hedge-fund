"""Persistent cache for LLM responses, keyed by everything that affects the output.

Avoids re-running the same agent analysis (same prompt, model, provider, and
output schema) across process restarts, e.g. re-running an aborted backtest.
"""

import hashlib
import json
import os
import threading
from pathlib import Path

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / ".cache" / "llm_cache.sqlite3"


def _is_enabled() -> bool:
    return os.environ.get("LLM_CACHE_ENABLED", "true").strip().lower() not in ("0", "false", "no")


def _serialize_prompt(prompt: any) -> str:
    """Render a prompt (raw string, ChatPromptValue, or list of messages) to a stable string."""
    if isinstance(prompt, str):
        return prompt

    if hasattr(prompt, "to_messages"):
        messages = prompt.to_messages()
    elif isinstance(prompt, list):
        messages = prompt
    else:
        return str(prompt)

    parts = []
    for message in messages:
        role = getattr(message, "type", message.__class__.__name__)
        content = getattr(message, "content", str(message))
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


class LLMCache:
    """SQLite-backed cache mapping (agent, model, schema, prompt) -> structured LLM response."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or Path(os.environ.get("LLM_CACHE_PATH", _DEFAULT_DB_PATH))
        self._lock = threading.Lock()
        self._conn = None
        if _is_enabled():
            self._connect()

    def _connect(self):
        import sqlite3

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                response_json TEXT NOT NULL,
                agent_name TEXT,
                model_name TEXT,
                model_provider TEXT,
                pydantic_model TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.commit()

    def make_key(
        self,
        *,
        agent_name: str | None,
        model_name: str,
        model_provider: str,
        pydantic_model_name: str,
        prompt: any,
    ) -> str:
        """Build a deterministic cache key from everything that affects the LLM's output."""
        digest_input = "|".join(
            [
                agent_name or "",
                str(model_provider),
                str(model_name),
                pydantic_model_name,
                _serialize_prompt(prompt),
            ]
        )
        return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> dict | None:
        if not self._conn:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT response_json FROM llm_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None

    def set(
        self,
        cache_key: str,
        response: dict,
        *,
        agent_name: str | None,
        model_name: str,
        model_provider: str,
        pydantic_model_name: str,
    ) -> None:
        if not self._conn:
            return
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO llm_cache
                    (cache_key, response_json, agent_name, model_name, model_provider, pydantic_model)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (cache_key, json.dumps(response), agent_name, model_name, str(model_provider), pydantic_model_name),
            )
            self._conn.commit()

    def clear(self) -> None:
        if not self._conn:
            return
        with self._lock:
            self._conn.execute("DELETE FROM llm_cache")
            self._conn.commit()


_llm_cache = LLMCache()


def get_llm_cache() -> LLMCache:
    """Get the global LLM response cache instance."""
    return _llm_cache
