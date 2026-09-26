"""Downstream AI explanation layer: a scored finding in, `{explanation, recommendation}` out.

It consumes findings only and is structurally incapable of altering type, severity or
confidence (see explainer.py).
"""

from .cache import MemoryCache, PostgresCache
from .contract import Explanation
from .explainer import Explainer, ExplainError
from .llm import AnthropicLLM

__all__ = [
    "AnthropicLLM",
    "ExplainError",
    "Explainer",
    "Explanation",
    "MemoryCache",
    "PostgresCache",
]
