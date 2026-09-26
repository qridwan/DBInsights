"""Statistical primitives for the ablation analysis. Pure functions over plain numbers.

Why these tests (the design constraint behind every choice below)
-----------------------------------------------------------------
The system under test is deterministic: for a fixed database, source tree and ground truth, a
configuration finds the same problems on every repetition. Repetitions therefore carry almost no
variance in the *accuracy* metrics, and only the runtime workload (seeded per repetition) and the
machine (timing) vary. Two consequences:

1. A test that treats repetitions as independent samples of accuracy (a t-test on 10 identical
   F1 values) is degenerate: zero variance gives an undefined statistic, and any nonzero
   difference would be "infinitely significant". It would also pseudo-replicate: 10 copies of the
   same 40 problems are not 400 problems. The honest unit for accuracy is the *problem*, not the
   repetition. So accuracy is compared on the 40 ground-truth problems, paired across
   configurations (each configuration is scored on the same problems), and the repetitions serve
   to show that the result is stable (zero variance across repetitions is reported, not hidden).

2. Timing (detection latency, overhead) is the opposite: it varies from repetition to repetition
   and is right-skewed. So it is compared across repetitions with rank-based tests.

Tests used
----------
* Exact McNemar test (two-sided binomial test on the discordant pairs) for "was this problem
  detected?", paired per problem. Two configurations judged on the same problems give paired
  binary outcomes; McNemar uses only the problems on which they differ, and the exact version
  is valid for the small numbers of discordant pairs we have (the chi-square approximation is
  not). Effect size: the paired risk difference (change in detection rate) and the discordant
  odds ratio b/c, which shows how lopsided the disagreements are.
* Percentile bootstrap for differences of precision and F1. Precision depends on false
  positives, which are not paired across configurations (different configurations emit different
  findings), so no paired test exists; the bootstrap resamples the ground-truth problems and the
  emitted findings and reports an interval for the difference. Bootstrap, because F1 is a ratio
  with a non-normal sampling distribution and n is small. Reported as an interval, not a p-value.
* Wilcoxon signed-rank test (paired, two-sided) for latency and overhead, paired by
  (app, repetition): configurations ran back to back in the same repetition, so the pairing
  removes machine drift between repetitions. Rank-based because run times are right-skewed and
  n = 20 pairs is too few to trust normality. Effect size: Cliff's delta (P(x>y) - P(x<y)),
  which is distribution-free and reads directly as dominance.
* Holm's step-down correction across the four named hypotheses tests: they are a family, and
  reporting four raw p-values inflates the chance that at least one looks significant by luck.
  Holm controls the family-wise error rate without assuming independence and is never less
  powerful than Bonferroni.

Confidence intervals
--------------------
Across repetitions: Student-t interval on the mean (n = 20 per app pair, or 10 per app). For
metrics with zero variance the interval collapses to a point, and is reported with `n_distinct`
so that is visible rather than looking like spurious precision. For accuracy, a percentile
bootstrap over problems is reported alongside, since that is where the real uncertainty lives.
"""

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from scipy import stats as scipy_stats

BOOTSTRAP_RESAMPLES = 10_000
CONFIDENCE = 0.95


@dataclass(frozen=True)
class MeanCI:
    n: int
    mean: float | None
    low: float | None
    high: float | None
    #: How many distinct values the mean is over. 1 means no variance: the interval is a point.
    n_distinct: int


def mean_ci(values: Sequence[float], confidence: float = CONFIDENCE) -> MeanCI:
    """Mean with a Student-t confidence interval."""
    n = len(values)
    if n == 0:
        return MeanCI(0, None, None, None, 0)
    mean = math.fsum(values) / n
    distinct = len(set(values))
    if n < 2 or distinct == 1:
        return MeanCI(n, mean, mean, mean, distinct)
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (n - 1))
    half = scipy_stats.t.ppf(0.5 + confidence / 2, n - 1) * sd / math.sqrt(n)
    return MeanCI(n, mean, mean - half, mean + half, distinct)


def bootstrap_ci(
    statistic: Callable[[random.Random], float | None],
    *,
    seed: int,
    resamples: int = BOOTSTRAP_RESAMPLES,
    confidence: float = CONFIDENCE,
) -> tuple[float | None, float | None]:
    """Percentile interval of `statistic`, which draws its own resample from the given RNG.

    Resamples where the statistic is undefined (e.g. precision with no findings) are dropped.
    """
    rng = random.Random(seed)
    draws = sorted(d for d in (statistic(rng) for _ in range(resamples)) if d is not None)
    if len(draws) < resamples // 2:
        return None, None
    tail = (1 - confidence) / 2
    return draws[int(tail * len(draws))], draws[min(int((1 - tail) * len(draws)), len(draws) - 1)]


@dataclass(frozen=True)
class McNemar:
    #: Detected under both / only under the first / only under the second / neither.
    both: int
    only_first: int
    only_second: int
    neither: int
    p_value: float
    #: second minus first, in detection rate.
    risk_difference: float
    #: only_second / only_first (inf when only_first is 0 and only_second is not).
    discordant_odds_ratio: float | None


def mcnemar_exact(first: Sequence[bool], second: Sequence[bool]) -> McNemar:
    """Exact two-sided McNemar test for paired detection outcomes (first vs second)."""
    if len(first) != len(second):
        raise ValueError("paired outcomes must have equal length")
    both = sum(a and b for a, b in zip(first, second, strict=True))
    only_first = sum(a and not b for a, b in zip(first, second, strict=True))
    only_second = sum(b and not a for a, b in zip(first, second, strict=True))
    neither = len(first) - both - only_first - only_second
    discordant = only_first + only_second
    p = 1.0 if discordant == 0 else scipy_stats.binomtest(only_first, discordant, 0.5).pvalue
    if only_first:
        odds: float | None = only_second / only_first
    else:
        odds = math.inf if only_second else None
    n = len(first)
    return McNemar(
        both,
        only_first,
        only_second,
        neither,
        p,
        (only_second - only_first) / n if n else 0.0,
        odds,
    )


@dataclass(frozen=True)
class Wilcoxon:
    n: int
    #: Pairs with a nonzero difference; the test uses only these.
    n_nonzero: int
    statistic: float | None
    p_value: float | None
    cliffs_delta: float | None
    median_difference: float | None


def cliffs_delta(first: Sequence[float], second: Sequence[float]) -> float | None:
    """P(second > first) - P(second < first) over all cross pairs; in [-1, 1]."""
    if not first or not second:
        return None
    greater = sum(b > a for a in first for b in second)
    smaller = sum(b < a for a in first for b in second)
    return (greater - smaller) / (len(first) * len(second))


def wilcoxon_paired(first: Sequence[float], second: Sequence[float]) -> Wilcoxon:
    """Paired Wilcoxon signed-rank test (two-sided) of second vs first, with Cliff's delta."""
    if len(first) != len(second):
        raise ValueError("paired samples must have equal length")
    diffs = [b - a for a, b in zip(first, second, strict=True)]
    nonzero = [d for d in diffs if d != 0]
    ordered = sorted(diffs)
    median = ordered[len(ordered) // 2] if len(ordered) % 2 else None
    if ordered and median is None:
        median = (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2
    if len(nonzero) < 1:
        return Wilcoxon(
            len(diffs), 0, None, 1.0 if diffs else None, cliffs_delta(first, second), median
        )
    result = scipy_stats.wilcoxon(nonzero, alternative="two-sided", method="auto")
    return Wilcoxon(
        len(diffs),
        len(nonzero),
        float(result.statistic),
        float(result.pvalue),
        cliffs_delta(first, second),
        median,
    )


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values, in the input order."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


Z95 = 1.959963984540054


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float | None, float | None]:
    """Wilson score interval for a proportion: stays inside [0, 1] and behaves at small n and at
    0% or 100%, where the normal approximation does not."""
    if n == 0:
        return None, None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(centre - half, 0.0), min(centre + half, 1.0)
