"""The model behind the explanation layer, behind a one-method interface.

The layer only needs `complete(system, user) -> text`. The Anthropic client is imported lazily so
the rest of the service (and every test) runs without the SDK or an API key.
"""

import os
from typing import Protocol

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 1024


class LLM(Protocol):
    #: Identifies the model in the cache version: a different model invalidates cached text.
    name: str

    def complete(self, system: str, user: str) -> str: ...


class AnthropicLLM:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        try:
            import anthropic
        except ImportError as error:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "the explanation layer's model client needs the `explain` extra: "
                "`uv sync --extra explain`"
            ) from error
        self.name = model or os.environ.get("DBINSIGHT_EXPLAIN_MODEL", DEFAULT_MODEL)
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def complete(self, system: str, user: str) -> str:
        reply = self._client.messages.create(
            model=self.name,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in reply.content if block.type == "text")
