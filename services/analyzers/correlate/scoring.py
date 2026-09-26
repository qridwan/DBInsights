"""How evidence is weighed. One small table of weights, one way to combine them.

Each piece of evidence contributes a weight in nats of log-odds (a natural-log likelihood
ratio): positive supports a hypothesis, negative contradicts it. Independent evidence adds.
Addition is commutative, and the weights are summed in a canonical (sorted) order with
`math.fsum`, so the same evidence always yields the same score, whatever order it arrived in.
Every weight below is a multiple of 0.5, so the sums are exact in binary floating point.

These weights are expert-set, not calibrated on data. Their job is to encode which kinds of
evidence outweigh which (a database index outweighs a suspicion drawn from a declaration), and
they are deliberately gathered here, in one place, so that M5's ablation can vary them.
Nothing else in the engine contains a number.

Confidence labels are cut from the same log-odds scale: a hypothesis is believed at log-odds
0 (posterior 0.5) and strongly believed at log(4) (posterior 0.8).
"""

import math
from collections.abc import Iterable
from typing import Literal

Confidence = Literal["LOW", "MEDIUM", "HIGH"]

#: What a layer's own confidence in the hypothesis it raised is worth.
PRIOR_LOGIT: dict[str, float] = {"HIGH": 1.5, "MEDIUM": 0.5, "LOW": -0.5}

#: Runtime saw one query shape repeat within a single request; scaled by how strongly.
RUNTIME_REPETITION_LOGIT: dict[str, float] = {"HIGH": 2.5, "MEDIUM": 1.5, "LOW": 0.5}

#: pg_catalog has an index that leads with a filtered column: a scan is not the cost.
INDEX_PRESENT_IN_DATABASE = -4.0
#: pg_catalog has no such index: the declared suspicion is confirmed by the real schema.
INDEX_ABSENT_FROM_DATABASE = 1.0

#: The database has no foreign-key constraint on a relation whose rows are orphaned:
#: orphans are possible, which explains them.
FOREIGN_KEY_NOT_ENFORCED = 1.5
#: The database enforces the constraint yet orphans are reported: they should be impossible.
FOREIGN_KEY_ENFORCED = -3.0

#: Log-odds at which a hypothesis is believed (posterior 0.5) and strongly believed (0.8).
BELIEVED_AT = 0.0
STRONGLY_BELIEVED_AT = math.log(4)

#: Decimal places of a reported posterior.
POSTERIOR_DIGITS = 6


def combine(weights: Iterable[float]) -> float:
    """Sum of weights, independent of the order they are given in."""
    return math.fsum(sorted(weights))


def posterior(logit: float) -> float:
    return round(1 / (1 + math.exp(-logit)), POSTERIOR_DIGITS)


def confidence_for(logit: float) -> Confidence:
    if logit >= STRONGLY_BELIEVED_AT:
        return "HIGH"
    return "MEDIUM" if logit >= BELIEVED_AT else "LOW"


def believed(logit: float) -> bool:
    return logit >= BELIEVED_AT
