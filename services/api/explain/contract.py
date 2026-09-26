"""What the explanation layer returns: two text fields, and nothing else.

`extra="forbid"` is the structural guard. A model reply that carries a `severity`, `confidence`,
`ruleId` or any other key does not validate, so it cannot be applied to a finding: there is no
field to receive it. The layer also never holds the finding it explains (see projection.py).
"""

from pydantic import BaseModel, ConfigDict, Field

MAX_TEXT = 2000


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    explanation: str = Field(min_length=1, max_length=MAX_TEXT)
    recommendation: str = Field(min_length=1, max_length=MAX_TEXT)
