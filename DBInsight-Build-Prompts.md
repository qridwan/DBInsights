# DBInsight — Build Prompt Playbook

**Prompts for implementing PMIT-6000 with Claude Code**
Ridwan · September 2026 · Companion to the Project Plan (M0–M8)

---

## How to use this

Three rules make the difference between a codebase that extracts cleanly into Phase 0 and one that has to be rewritten.

**One milestone step per session.** Claude Code drifts over long sessions — it starts inventing test-app-specific shortcuts around turn forty. Start a fresh session per numbered prompt below. If a session runs long, end it and start a new one rather than pushing through.

**`CLAUDE.md` is not optional.** Section 1 below is a file you put at the repo root before writing any code. It carries the constraints from §3 of the Project Plan — the ones that decide whether the thesis code becomes the product core for free or has to be ported. Claude Code reads it automatically each session; without it, every session rediscovers the architecture from scratch and gets it slightly wrong each time.

**Verify against exit criteria, not against "it works".** Each milestone ends with a verification prompt. Run it in a *fresh session* so the model checking the work has not spent an hour convincing itself the work is correct.

A note on what these prompts cannot do: M6's labelling, the supervisor conversations, and every scope decision are human judgment. Section 5 lists them explicitly so you do not waste time trying to automate them.

---

## 1. `CLAUDE.md` — write this first

Put this at the repo root before the first line of code. Edit it as decisions change; treat it as the project's constitution.

```markdown
# DBInsight

Research implementation for PMIT-6000 (IIT-JU). A hybrid static and runtime
analysis framework detecting database performance and data-quality problems
in Prisma/PostgreSQL applications.

## Non-negotiable constraints

These exist because the static core is extracted into a standalone developer
tool after the thesis defense. Violating them turns that extraction into a
rewrite. Do not violate them for convenience.

1. All static detection lives in `packages/core` (TypeScript). Rule functions
   are pure: `(context: AnalysisContext) => Finding[]`. No HTTP, no filesystem
   walking, no database access inside a rule.
2. The analyzer's only input is `{ sourceDir, schemaPath }`. It must work on
   any Prisma project, not just our test apps.
3. NEVER write logic keyed to our test applications — no hardcoded model names
   ("Product", "Post"), file paths, or table names anywhere in `packages/core`.
   If a test needs specific data, it goes in a fixture, not in a rule.
4. `Finding` carries `schemaVersion` from the first commit. Never change its
   shape without bumping that field.
5. Every rule assigns explicit `confidence` and `evidence[]`, even when the
   evidence is static-only.
6. `fingerprint` must be stable when unrelated lines shift. Derive it from
   (ruleId, filePath, enclosingFunctionName, normalizedCallExpression).
   Never include line numbers.

## Language split

TypeScript (`packages/core`) — extracted into the product later:
  - schema.prisma parsing
  - ts-morph ORM analysis and data-flow resolution
  - rules, confidence assignment
  - the Finding model

Python (`services/`) — thesis only, never extracted:
  - SQL analysis (SQLGlot)
  - runtime query statistics
  - data-quality profiling, anomaly detection
  - correlation engine
  - experiment harness
  - FastAPI service

The Python service invokes the TypeScript analyzer as a subprocess over a
JSON stdin/stdout contract. Never reimplement TS analysis logic in Python.

## Layout

packages/core/        TypeScript static analysis core
packages/cli/         CLI wrapper (post-defense, Phase 0)
services/api/         FastAPI — orchestration
services/analyzers/   Python — SQL, data quality, anomaly, correlation
services/experiments/ Ablation harness, ground-truth scoring
apps/ecommerce/       Test application 1 (Prisma + Postgres)
apps/blog/            Test application 2 (Prisma + Postgres)
apps/dashboard/       Next.js dashboard (M8)
fixtures/             Analyzer test fixtures — synthetic, minimal

## Stack

TypeScript: ts-morph, vitest. Python: FastAPI, Pydantic, SQLGlot, pandas,
scipy, pytest. Postgres 16. Docker Compose for everything.

## Research context that constrains design

- Approach B (static source + declared schema) must run with NO database
  connection. Never introduce a DB dependency into anything Approach B uses.
- The declared schema (schema.prisma) and the actual schema (information_schema)
  are SEPARATE evidence sources and must never be merged into one abstraction.
  Measuring their divergence is RQ6.
- The AI explanation layer consumes findings only. It must be structurally
  incapable of altering type, severity, or confidence.

## Conventions

- Conventional commits.
- Every rule ships with fixture tests: one true positive, one near-miss that
  must NOT fire.
- No new dependency without justification in the PR description.
- When unsure whether something belongs in core or services, ask rather than
  guess — the boundary is load-bearing.
```

---

## 2. Milestone prompts

### M0 — Foundations

**M0.1 — Scaffold**

```
Set up the DBInsight monorepo per the layout in CLAUDE.md.

- pnpm workspaces for packages/core and packages/cli
- packages/core: TypeScript strict mode, vitest, ts-morph as a dependency,
  builds to ESM + CJS
- services/: Python 3.12, uv for dependency management, pytest, ruff
- docker-compose.yml with Postgres 16 and a named volume
- GitHub Actions running both test suites on push
- Root README stating what the project is in three sentences

Create packages/core/src/models.ts with the Finding and Evidence interfaces
exactly as specified in CLAUDE.md constraint 4, plus Severity and Confidence
as string union types. Export an `analyze()` signature that throws
"not implemented" for now.

Do not implement any analysis logic in this step.
```

**M0.2 — Test applications**

```
Set up the two test applications under apps/ecommerce and apps/blog.

Requirements for each:
- Next.js App Router + Prisma + PostgreSQL
- A realistic schema (ecommerce: products, categories, orders, customers,
  reviews; blog: posts, authors, comments, tags)
- Seed script producing enough rows that query patterns have observable cost
  (ecommerce: ~5000 products, ~20000 orders; blog: ~2000 posts, ~15000 comments)
- API routes exercising realistic read paths — listing, detail, search,
  aggregation
- Both must run from a single `docker compose up`

Write CLEAN code at this stage. Do NOT introduce any performance problems or
anti-patterns — those are injected deliberately in M2 and must be absent now
so M1 can establish a zero-false-positive baseline.
```

**M0.3 — Exit check** *(fresh session)*

```
Verify M0 exit criteria and report pass/fail per item with evidence:

1. Both test apps start from one docker compose command and their seed
   scripts complete
2. packages/core builds and its (empty) test suite runs in CI
3. Finding model matches CLAUDE.md constraint 4 exactly
4. No analysis logic exists yet anywhere

Do not fix anything. Report only.
```

---

### M1 — Static core + declared schema

**M1.1 — Schema parser**

```
Implement packages/core/src/schema/parse.ts.

Parse a schema.prisma file into a SchemaModel:
- models with fields (name, type, optional, list)
- relations (including the referenced model and scalar FK fields)
- declared indexes from @@index, @@unique, @unique, @id, @@id
- for composite indexes, preserve FIELD ORDER — leading position matters for
  index-coverage decisions later

Write it as a real parser over the Prisma schema grammar. Do not use regex
line matching; it will break on multi-line blocks and attribute arguments.

Tests: fixtures under fixtures/schemas/ covering single-field index, composite
index, @unique vs @@unique, relations with explicit and implicit FK fields,
and a schema with no indexes at all.

No database access. No test-app-specific assumptions.
```

**M1.2 — ORM call location**

```
Implement packages/core/src/analyze/orm-calls.ts using ts-morph.

Locate every Prisma client call in a source directory and extract the
ORMOperation shape:

interface ORMOperation {
  file: string; line: number;
  model: string; operation: string;
  args: { hasWhere, whereFields[], hasTake, hasSkip, hasCursor,
          hasSelect, includeRelations[] };
  loopContext: { inLoop, loopKind, iteratesOverORMResult,
                 sourceOperationLine } | null;
  enclosingFunction: string | null;
  isAwaited: boolean;
  siblingAwaits: number;
}

This step: everything EXCEPT iteratesOverORMResult and sourceOperationLine —
set those to false/null for now. M1.3 resolves them.

Handle: direct calls (prisma.user.findMany), calls through a destructured
client, calls inside arrow functions and class methods, and calls where the
client is imported from a shared module.

Tests: fixtures under fixtures/source/ for each of those shapes.
```

**M1.3 — Data-flow resolution**

```
Implement packages/core/src/analyze/dataflow.ts.

Resolve iteratesOverORMResult: given a Prisma call inside a loop, determine
whether the loop's iterable resolves to the result of an earlier Prisma call
in the same scope.

Use ts-morph's symbol resolution — the TypeScript type checker — not
syntactic guessing. Handle:
- for-of over a variable assigned from an awaited Prisma call
- .map() / .forEach() chained directly onto an awaited Prisma call
- .map() over a variable assigned from a Prisma call
- the same through one level of intermediate assignment

MUST return false for: loops over literal arrays, loops over function
parameters of unknown origin, loops over fetch() results, loops over
Object.keys().

Set sourceOperationLine to the line of the originating Prisma call when
resolution succeeds.

This is the most important function in the project — R1's precision depends
entirely on it. Write the negative-case fixtures FIRST, then make them pass.
```

**M1.4 — Rules**

```
Implement the five Phase 0 rules in packages/core/src/rules/.

R1 N_PLUS_ONE_IN_LOOP (HIGH severity)
  Prisma call inside a loop. Confidence HIGH when iteratesOverORMResult is
  true; MEDIUM when in a loop but unresolved.

R2 MISSING_INDEX_ON_FILTERED_FIELD (HIGH severity)
  A field appears in a where clause in code AND schema.prisma declares no
  @@index / @unique / @id / leading composite position covering it.
  Only fire on findMany/findFirst/count — not on unique lookups.
  This is the project's most differentiated rule. Be conservative.

R3 UNBOUNDED_MUTATION (HIGH severity)
  deleteMany() or updateMany() with no where argument.

R4 SEQUENTIAL_INDEPENDENT_AWAITS (MEDIUM severity)
  Two or more awaited Prisma calls in one block with no data dependency
  between them.

R5 MISSING_PAGINATION (MEDIUM severity)
  findMany() with no take/skip/cursor.

Each rule: a pure function (context) => Finding[], explicit confidence and
evidence[], a stable fingerprint per CLAUDE.md constraint 6, and a
suggestedFix as a markdown code block.

Each rule ships with at least one true-positive fixture AND one near-miss
fixture that must not fire.
```

**M1.5 — Wire up and baseline**

```
Implement analyze({ sourceDir, schemaPath }) in packages/core/src/index.ts,
running the schema parser, ORM call location, data-flow resolution and all
five rules, returning Finding[].

Then run it against apps/ecommerce and apps/blog.

Expected result: ZERO findings. Both apps were written clean in M0.

For every finding produced, diagnose whether it is a genuine problem in the
test app (fix the app) or a false positive (fix the rule). Report each
decision and its reasoning. Do not suppress findings to reach zero.
```

**M1.6 — Exit check** *(fresh session)*

```
Verify M1 exit criteria. For each, state pass/fail with the evidence you used:

1. analyze() accepts an arbitrary Prisma project — prove it by grepping
   packages/core for any hardcoded model name, table name, or path from our
   test apps. Report every match.
2. Data-flow resolution distinguishes ORM-result loops from literal-array
   loops — run the negative fixtures and report.
3. Zero findings on both test apps pre-injection.
4. Every rule has both a positive and a near-miss fixture.

Do not fix anything. Report only.
```

---

### M2 — Ground truth injection

**M2.1 — Manifest format**

```
Design and implement the ground-truth manifest format in
services/experiments/groundtruth/.

Requirements:
- Machine-readable (JSON or YAML), one manifest per test app
- Each entry: id, problemType, category (performance | data_quality |
  schema_divergence), file, line (or table/column for data problems),
  expectedRuleId, description, injectedAt
- A Python loader validating it with Pydantic
- A scorer that takes Finding[] plus a manifest and computes TP/FP/FN
  per problem type and in aggregate

The scorer must be the ONLY path by which results are computed. No manual
counting anywhere in the pipeline.

Write the scorer's tests with synthetic findings and manifests before
injecting anything.
```

**M2.2 — Performance problems**

```
Inject performance problems into both test apps, recording each in the
ground-truth manifest.

Per app, at least 3 instances of each:
- N+1 query (loop over an ORM result issuing a per-item query)
- Missing index (a where clause on an unindexed field, with real query cost)
- Excessive relation loading (include pulling far more than the endpoint uses)
- Repeated identical query within one request
- Large unpaginated findMany

Each must be reachable through an HTTP endpoint so M3's runtime collector can
observe it. Note the endpoint path in the manifest entry.

Make them realistic. They should look like code a competent developer would
plausibly write under deadline — not obviously wrong. If an injected problem
is so blatant no real codebase would contain it, the experiment measures
nothing.
```

**M2.3 — Data-quality and divergence problems**

```
Inject data-quality problems into the seed data and schema-divergence
problems into the migration history. Record all in the manifest.

Data quality (3+ instances each, across both apps):
- NULL spike in a column that is normally populated
- Duplicate spike on a field expected to be near-unique
- Category distribution shift versus the historical baseline
- Referential inconsistency (orphaned FK rows)

Schema divergence, BOTH directions:
- An index created by a raw SQL migration and never reflected in
  schema.prisma (actual has it, declared does not)
- An index declared in schema.prisma but dropped by a later raw SQL
  migration (declared has it, actual does not)

The divergence cases are the controlled instances RQ6 measures. Make the
migration history realistic — the raw SQL migration should look like a
normal operational fix, not an artificial plant.
```

**M2.4 — Exit check** *(fresh session)*

```
Verify M2 exit criteria:

1. Manifest is machine-readable, validates, and drives the scorer with no
   manual tallying anywhere
2. Every performance problem is reachable through an HTTP endpoint — list
   each endpoint and confirm it responds
3. At least 3 instances of every problem type — produce the count table
4. Divergence cases exist in both directions

Then run the M1 analyzer against both injected apps and report which injected
problems it currently catches. This is the Approach B pre-measurement; do not
tune anything based on it.
```

---

### M3 — Runtime + actual schema

**M3.1 — Actual schema reader**

```
Implement services/analyzers/schema/actual.py.

Read PostgreSQL information_schema and pg_catalog to produce an ActualSchema:
tables, columns with types and nullability, indexes (with column order and
uniqueness), foreign keys, constraints.

Then implement a divergence comparator taking a SchemaModel (from the TS
parser, via JSON) and an ActualSchema, reporting:
- indexes in actual but not declared
- indexes in declared but not actual
- column type or nullability mismatches

Keep these two schema sources as separate types throughout. Do NOT create a
unified "Schema" abstraction that merges them — measuring their divergence is
RQ6 and merging them destroys the measurement.
```

**M3.2 — Runtime collector**

```
Implement the Prisma runtime collector and the query fingerprinting module.

Collector: a Prisma client extension capturing per query — timestamp,
request id, route, model, operation, duration, rows returned, and the
generated SQL where available. Emit to a collector endpoint; never block the
request path.

Fingerprinting: normalize queries so literal values collapse into one shape.

CRITICAL failure mode to handle explicitly: pg_stat_statements-style
normalization is known to be OVER-granular for ORM-generated SQL — one
logical query shape fragments into many distinct ids, which would make
per-request repetition counting under-count and produce false negatives for
N+1. Normalize at the AST level, not by literal substitution alone.

Write a test that generates the same logical Prisma query with varying
argument counts (e.g. `where: { id: { in: [...] } }` with 1, 5, 50 ids) and
asserts they collapse to ONE fingerprint.
```

**M3.3 — Load harness and runtime N+1**

```
Implement services/experiments/load/ — a reproducible load harness that
exercises every endpoint recorded in the ground-truth manifests, and runtime
N+1 detection over the collected data.

Load harness: fixed request sequence, fixed seed, configurable repetitions.
Query counts across runs must vary by under 5%.

Runtime N+1: within one request id, the same fingerprint executing more than
a threshold number of times, with the count and the route reported as
evidence.

Measure and record the collector's overhead — request latency with the
collector on versus off, plus its CPU and memory cost. This is RQ5 data, not
an afterthought; store it in the results database with the same rigor as
detection results.
```

**M3.4 — Exit check** *(fresh session)*

```
Verify M3 exit criteria:

1. Fingerprinting collapses ORM argument-count variants to one shape — run
   that test and report
2. Load harness repeatable within 5% variance — run it 5 times and report
   the actual variance
3. Collector overhead measured and stored
4. Divergence detected on both M2 injected divergence cases

Report only.
```

---

### M4 — Data quality, anomaly, correlation

**M4.1 — Data-quality profiler**

```
Implement services/analyzers/dataquality/.

Per table and column: row count, NULL count and rate, distinct count
(cardinality), duplicate rate on near-unique columns, and category frequency
distribution for low-cardinality columns.

Store profiles with a timestamp so a history accumulates — the anomaly
detector compares against learned baselines, not fixed thresholds.

Also implement referential integrity checks against the declared relations.
```

**M4.2 — Anomaly detector**

```
Implement services/analyzers/anomaly/ using interpretable methods only:
Z-score, IQR, and moving average with moving standard deviation.

Each detector takes a metric history and a current observation, returning
whether it falls outside the learned expected range, with the range reported
as evidence.

Explicit requirement: NO fixed thresholds. A detector that fires on
"NULL rate > 10%" is wrong; it must fire on "NULL rate outside the range
predicted from this column's own history".

Seed history by profiling the clean seed data across simulated time windows
before the M2 data-quality problems are applied.

Do not implement Isolation Forest yet — it is an optional stretch arm.
```

**M4.3 — Correlation engine**

```
Implement services/analyzers/correlate/ — merging static, declared-schema,
actual-schema, runtime and data-quality evidence into single scored findings.

Rules of the engine:
- A finding carries evidence from every layer that contributed, with each
  evidence item naming its source layer
- Confidence is raised or lowered by corroborating or contradicting evidence
- Contradicting evidence must be able to CHANGE a finding's type, not just
  its confidence

The canonical test case, which must pass: a static N+1 suspicion, plus
runtime evidence showing the query executing hundreds of times per request,
plus schema evidence showing the joined column IS indexed, must resolve to
an N+1 finding — NOT to a missing-index finding. Write this test first.

Confidence scores must be reproducible: identical input produces identical
scores across runs.
```

**M4.4 — Exit check** *(fresh session)*

```
Verify M4 exit criteria:

1. Anomaly detection uses learned baselines — grep for any hardcoded
   numeric threshold in the detectors and report every match
2. The canonical correlation test passes (N+1 not missing-index)
3. Confidence scores reproducible — run the full pipeline twice on identical
   input and diff the scores

Report only.
```

---

### M5 — Controlled experiment + ablation

**M5.1 — Ablation harness**

```
Implement services/experiments/ablation/ running six configurations against
both test apps.

Config    Static ORM  SQL  Declared  Actual  Runtime  Data
A         no          yes  no        no      no       no
B1        yes         yes  no        no      no       no
B2        yes         yes  yes       no      no       no
C1        yes         yes  yes       yes     no       no
C2        yes         yes  yes       yes     yes      no
C3        yes         yes  yes       yes     yes      yes

Each configuration is a declarative set of enabled evidence layers — NOT six
code paths. The pipeline reads the config and enables layers accordingly.

Per configuration and app: run at least 10 repetitions, score each against
the ground-truth manifest, and record precision, recall, F1, false-positive
rate, detection latency, and analysis overhead per run.

Results go to a Postgres results table, one row per (config, app, repetition,
problemType). Never aggregate at write time — aggregation happens at analysis
time so the raw data stays available.

Everything must be reproducible from a single command.
```

**M5.2 — Statistical analysis**

```
Implement services/experiments/analysis/ producing the results the thesis
reports.

For each metric, per configuration: mean with 95% confidence interval across
repetitions. Never report a single-run number.

Significance testing on the pairwise comparisons that answer the research
questions:
- B1 vs B2 — what the declared schema contributes (H5, RQ6)
- B2 vs C1 — what a live database adds over the declared schema (RQ6 core)
- C1 vs C2 — what runtime contributes (H3, RQ3)
- A vs C3 — the headline hybrid-versus-baseline comparison (H1)

Use an appropriate test for the distribution and justify the choice in a
comment. Report effect sizes, not only p-values.

Also produce the per-problem-type breakdown — aggregate-only results hide
that a configuration may help one problem type and hurt another.

Output: a results JSON plus matplotlib figures suitable for the thesis.
```

**M5.3 — Exit check** *(fresh session)*

```
Verify M5 exit criteria:

1. 10+ repetitions per configuration — report actual counts
2. All results reported as means with confidence intervals
3. Significance tests present for the four named comparisons, with effect
   sizes
4. Per-problem-type breakdown exists
5. The whole experiment reproduces from one command — run it and confirm

Then summarize the findings plainly, INCLUDING any result that contradicts
the hypotheses. A configuration performing worse than expected is a valid
result and must not be smoothed over.
```

---

### M6 — Real-world validation

> Runs in parallel with M3–M5. Depends on M1 only.

**M6.1 — Repository selection**

```
Build a candidate list of open-source projects using Prisma with PostgreSQL
for the real-world validation study.

Selection criteria — document these BEFORE searching, and apply them
mechanically:
- Uses Prisma with a committed schema.prisma
- Non-trivial: more than ~20 models or more than ~5k lines of TypeScript
- Active: a commit within the last 12 months
- Permissively licensed
- Not a tutorial, starter template, or Prisma's own examples

Produce a table of 20+ candidates with URL, star count, model count, LOC,
last commit date, and license. Record the search method so the selection is
reproducible.

Do not filter by whether the analyzer finds anything in them — that would
bias the sample.
```

**M6.2 — Batch analysis**

```
Build a harness that clones each selected repository at a pinned commit, runs
the Approach B analyzer (static + declared schema, no database), and stores
every finding with its repository, commit SHA, rule id, file, line, and
confidence.

Output a labelling worksheet: one row per finding, with the surrounding source
context (10 lines either side) and the relevant schema excerpt included, plus
empty columns for label and rationale.

Do NOT label anything. Do not judge whether findings are correct. Labelling
is a human step with a protocol written in advance.
```

**M6.3 — Analysis of labels** *(after you have labelled)*

```
I have completed labelling in [worksheet path]. Compute:

- Per-rule real-world precision, with confidence intervals
- Overall precision across all rules
- Cohen's kappa on the double-labelled 20% sample
- A breakdown of false-positive causes, grouped by what went wrong
- Specifically for R2: how often was an index present in the database but
  absent from schema.prisma? This is the real-world RQ6 divergence number.

Then compare per-rule real-world precision against the controlled-experiment
precision from M5 and discuss any rule where they diverge significantly.
That divergence is itself a finding.
```

---

### M7 — Adapter generalisation *(optional — first to cut)*

**M7.1 — MySQL adapter**

```
Add a MySQL adapter behind the existing DatabaseAdapter interface.

Success criterion: the core analyzer runs against a MySQL-backed Prisma app
with NO changes to packages/core and no changes to any rule. If the core
needs changing, that is a finding about the adapter abstraction — report it
rather than working around it.

Port one test app to MySQL, re-run the injected problem set, and report
differences from the Postgres baseline.
```

**M7.2 — Drizzle adapter**

```
Add a Drizzle ORM adapter behind the ORMAdapter interface.

Drizzle's query API differs substantially from Prisma's — the ORM call
locator and data-flow resolution need a Drizzle-specific implementation, but
the RULES must not change. If a rule needs modifying to accommodate Drizzle,
that is a finding about the rule abstraction; report it.

Scope: R1 and R2 only. Do not port all five rules.
```

---

### M8 — Dashboard, AI layer, write-up

**M8.1 — Dashboard**

```
Build apps/dashboard — Next.js, TypeScript, Tailwind, Recharts.

Views:
- Project health: finding counts by severity, trend over scans
- Findings list: filterable by severity, confidence, rule, evidence layer;
  each finding shows its full evidence chain with each item's source layer
  labelled
- Query analytics: slowest and most frequent fingerprints, per-endpoint
  repetition counts
- Data quality: per-column NULL rate, duplicates, cardinality, with the
  anomaly baseline range drawn alongside the current value
- Schema divergence: declared versus actual, side by side

The evidence chain is the point of this dashboard. A finding that shows only
a verdict without showing which layers contributed is a failed design.

Must demonstrate the end-to-end N+1 scenario convincingly in under 5 minutes.
```

**M8.2 — AI explanation layer**

```
Implement services/api/explain/ — the downstream AI explanation layer.

Contract: input is a fully-scored Finding. Output is { explanation,
recommendation } validated by Pydantic. Nothing else.

Structural requirement: the layer must be INCAPABLE of altering type,
severity, or confidence. Do not pass a mutable finding into it. Pass a
read-only projection containing only what the explanation needs, and return
only the two text fields. Write a test asserting that a finding's score is
byte-identical before and after explanation.

Cache by (ruleId, hash(evidence)) so identical findings across a codebase do
not trigger repeated calls.

System prompt must instruct: explain only the evidence given; never assert
problems not in the evidence; never dispute the severity.
```

**M8.3 — Thesis results chapter**

```
Draft the results chapter from the M5 and M6 outputs.

Structure per research question RQ1 through RQ6: what was measured, the
numbers with confidence intervals, what the result means, and what it does
not support.

Requirements:
- Every claim traces to a specific number in the results
- Report results that contradict the hypotheses with the same prominence as
  those that support them
- Distinguish controlled-experiment results (M5) from real-world results (M6)
  explicitly — never blend them into one claim
- Include the threats to validity: synthetic test applications, sample size
  in M6, single-ORM scope, and the labelling subjectivity in M6

Do not write a conclusion that overstates. The contribution is the
correlation and its measurement, not a claim to have beaten existing tools.
```

---

## 3. Recurring prompts

Use these between milestones, in fresh sessions.

**Constraint audit** — run after every milestone

```
Audit the repository against the non-negotiable constraints in CLAUDE.md.
For each of the six constraints, report every violation with file and line.

Pay particular attention to constraint 3: grep packages/core for any model
name, table name, column name, or path that appears in apps/ecommerce or
apps/blog. Report every match, even if it looks incidental.

Report only. Do not fix.
```

**Boundary check** — run whenever you add to services/

```
Check whether anything in packages/core has acquired a dependency on a
database, an HTTP client, the filesystem beyond reading the files it was
given, or any Python service.

Also check the reverse: has any static analysis logic been reimplemented in
Python instead of calling the TypeScript analyzer?

Report violations with file and line.
```

**Approach B purity** — run before any M5 experiment run

```
Verify that the Approach B configuration (static ORM + SQL + declared schema)
executes with NO database connection.

Prove it: run the B2 configuration with the Postgres container stopped. It
must complete and produce findings. If it fails or hangs, find what
introduced the database dependency.
```

**Reproducibility check** — run before writing up

```
Run the full experiment pipeline twice from a clean state on identical input.
Diff the results.

Anything that differs between runs is non-deterministic and must be either
fixed or explicitly documented as a source of variance in the thesis. Report
every difference.
```

---

## 4. Session discipline

**Start each session** with the milestone step and nothing else. If you find yourself pasting three prompts into one session, stop — the constraint violations start there.

**When Claude Code proposes a shortcut** that touches a CLAUDE.md constraint — hardcoding a model name for a test, putting analysis in Python because it is quicker, merging declared and actual schema into one type — say no and state which constraint. These are exactly the compromises that turn the extraction into a rewrite, and they always look reasonable in the moment.

**Run exit checks in fresh sessions.** A session that has spent an hour building something is a bad judge of whether it meets the criteria.

**Commit per prompt.** One prompt, one reviewable commit. It makes the constraint audits meaningful and gives you a clean history for the thesis appendix.

---

## 5. What these prompts cannot do

Be clear with yourself about the parts that are human judgment and do not attempt to automate them:

**M6 labelling.** Deciding whether a finding in someone else's codebase is a true positive requires understanding that codebase's intent. This is the single most valuable step in the plan and it is entirely manual. Budget real time for it.

**Whether an injected problem is realistic.** M2 asks for problems that look like code a competent developer would plausibly write. Only you can judge that, and if you get it wrong the experiment measures nothing.

**Scope decisions.** Whether to cut M7, whether to reduce M6's sample, whether to accept a fallback — these change what the thesis claims and belong to you and your supervisor.

**The supervisor conversation about the timeline.** The submitted proposal carries a sixteen-week schedule; this plan implies eight to twelve months. That has to be settled with a person.

**Deciding a negative result is real.** If the hybrid approach does not beat Approach B by much, the temptation to tune until it does will be strong. Recognising that a mixed result is the honest finding is the part of research no prompt covers.
