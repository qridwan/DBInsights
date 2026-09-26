# Real-world validation: repository selection protocol (M6.1)

Written before any search was run. `select_repos.py` records this file's SHA-256 in its output, so
a result can be tied to the exact protocol that produced it. Changing a rule after seeing
candidates means re-running the whole selection and recording a new protocol version.

## What the study is for

Measure the real-world precision of the static (Approach B) rules on projects the author did not
write. The sample must therefore not depend on what the analyzer finds. **The analyzer is never
run during selection**, and no rule below refers to its behaviour.

## Inclusion criteria (all must hold)

| # | Criterion | Mechanical test |
|---|---|---|
| I1 | Uses Prisma with PostgreSQL and a committed schema | The repository contains a file named `schema.prisma` whose `datasource` block has `provider = "postgresql"` (or `"postgres"`). |
| I2 | Non-trivial | `models >= 20` **or** `TypeScript LOC >= 5000`. Models: lines matching `^model\s+\w+` in the schema. LOC: physical lines in `.ts`/`.tsx` files, excluding `node_modules`, `dist`, `build`, `.next`, `generated`, and `*.d.ts`. |
| I3 | Active | Latest commit on the default branch is dated within 12 months before the selection date. |
| I4 | Permissively licensed | GitHub-detected SPDX id in {MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, Unlicense}. No license, `NOASSERTION`, GPL/AGPL/LGPL/MPL and others are excluded. |
| I5 | Not tutorial / starter / template / examples | None of E1-E4 below. |

## Exclusions (any one excludes)

| # | Test |
|---|---|
| E1 | Repository is a fork, is archived, or is flagged as a GitHub template. |
| E2 | Owner is `prisma` or `prisma-labs`. |
| E3 | Name, description or topics match, case-insensitively: `starter`, `boilerplate`, `template`, `tutorial`, `example`, `demo`, `course`, `learn`, `workshop`, `playground`, `sample`, `bootcamp`, `cheatsheet`, `awesome`. |
| E4 | A generated multi-project mirror: the repository has no TypeScript (language bytes for TypeScript = 0). |

The word filter in E3 is blunt and will exclude some genuine projects whose description mentions
one of the words. That is accepted: it is applied identically to every candidate, and every
exclusion is recorded with its reason so it can be audited.

## Search method (version 2)

**Change from version 1** (SHA-256 `38397b6b6ea0...`, superseded before any candidate was
inspected): version 1 enumerated every matching repository. Counting the pool showed that is
infeasible: code search reports 319,488 `schema.prisma` files mentioning postgresql, and
repository search reports 22,366 TypeScript repositories with the `prisma` topic, while the API
returns at most 1000 results per query. Only counts were looked at; no repository was read or
analysed. Version 2 replaces exhaustive enumeration with a pre-registered random sample of a
pool that is enumerable, so the selection stays unbiased with respect to what the analyzer finds.

1. **Pool.** Repository search (`GET /search/repositories`), one query family per permitted
   license L in {mit, apache-2.0, bsd-2-clause, bsd-3-clause, isc, 0bsd, unlicense}:
   `topic:prisma language:TypeScript license:L fork:false archived:false pushed:>2025-09-26 stars:A..B`.
   Each is sharded by star range, splitting a range in half until it returns at most 1000
   results, so the pool is complete for those qualifiers. The qualifiers are only *prefilters*
   that mirror E1, I3, I4 and E4; every candidate is still put through the full tests below.
   Shard boundaries and result counts are recorded.
2. **Order.** The pool is sorted by `owner/name` and shuffled with the fixed seed `20261001`.
3. **Decision.** Candidates are evaluated in that order. For each, stop at the first failing
   test and record it: E1, E2, E3 (metadata), I4 (license), I3 (last commit on the default
   branch), I1 (locate `schema.prisma` files, check the provider), E4, I2 (models from the schema;
   only if fewer than 20 models, a shallow clone to count TypeScript lines).
4. **Stopping.** Evaluation stops when 40 candidates are eligible (or the pool is exhausted).
   The candidate list is those 40; the **study set is the first 30 eligible in evaluation
   order**. Because the order is a seeded shuffle, neither list depends on stars, size,
   activity, or analyzer output. If fewer than 20 are eligible, that is reported and the
   criteria are not relaxed.
5. When a repository has several `schema.prisma` files, use the one with the most models and
   record how many there were.
6. Queries, dates, shard counts, evaluation order and the per-candidate decision are written to
   `candidates.json`. The pinned commit SHA of each eligible repository makes the *analysis*
   reproducible exactly, even though GitHub's index changes over time.

## Recorded per candidate

URL, stars, models, TypeScript LOC, last commit date and SHA, default branch, license (SPDX),
path of the chosen schema and count of schema files, and the decision with its reason.

## Known limits (to be stated in the thesis)

- The pool is repositories carrying the `prisma` topic. Projects that use Prisma without the
  topic are not sampled, and the topic is more common on tutorial and hobby projects.
- Open-source Prisma projects that are popular enough to be indexed differ from private ones.
- I1 requires a single file named `schema.prisma`; projects using Prisma's multi-file schema
  folders under other names are not found. This is independent of analyzer output.
- E3 removes some genuine projects (see above).
