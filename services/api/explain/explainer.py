"""Explains a fully-scored finding. Input: a Finding. Output: `Explanation`. Nothing else.

Why this layer cannot change a finding's score
----------------------------------------------
1. The finding is projected to a frozen `FindingView` at the door; the model-facing code only
   ever holds the view, which has no reference back to the finding.
2. The only thing returned is `Explanation`, which has exactly two text fields and rejects any
   other key. There is nowhere for a severity or confidence to go.
3. The method neither receives nor returns a mutable finding, and never writes to one.
A test asserts a finding serialises byte-identically before and after explanation.
"""

import json
import re

from pydantic import ValidationError

from analyzers.finding import Finding

from .cache import ExplanationCache, MemoryCache, evidence_hash
from .contract import Explanation
from .llm import LLM
from .projection import FindingView, project
from .prompt import PROMPT_VERSION, SYSTEM_PROMPT, user_message


class ExplainError(RuntimeError):
    """The model's reply could not be turned into a valid explanation."""


def parse_reply(text: str) -> Explanation:
    """The reply must be one JSON object holding exactly `explanation` and `recommendation`."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    try:
        return Explanation.model_validate(json.loads(stripped))
    except (json.JSONDecodeError, ValidationError) as error:
        raise ExplainError(f"reply is not a valid explanation: {error}") from error


class Explainer:
    def __init__(self, llm: LLM, cache: ExplanationCache | None = None, retries: int = 1) -> None:
        self._llm = llm
        self._cache = cache if cache is not None else MemoryCache()
        self._retries = retries
        #: Model calls made, for callers that want to show cache effectiveness.
        self.calls = 0

    @property
    def version(self) -> str:
        return f"{PROMPT_VERSION}:{self._llm.name}"

    def explain(self, finding: Finding) -> Explanation:
        view = project(finding)
        return self._explain_view(view)

    def _explain_view(self, view: FindingView) -> Explanation:
        digest = evidence_hash(view)
        cached = self._cache.get(view.rule_id, digest, self.version)
        if cached is not None:
            return cached
        message = user_message(view)
        last: ExplainError | None = None
        for _ in range(1 + self._retries):
            self.calls += 1
            try:
                result = parse_reply(self._llm.complete(SYSTEM_PROMPT, message))
            except ExplainError as error:
                last = error
                continue
            self._cache.put(view.rule_id, digest, self.version, result)
            return result
        raise last  # type: ignore[misc]
