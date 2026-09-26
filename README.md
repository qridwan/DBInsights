# DBInsight

DBInsight is a hybrid static and runtime analysis framework that detects database performance and data-quality problems in Prisma/PostgreSQL applications. Its TypeScript core analyzes application source and the declared `schema.prisma` without a database connection, while Python services add SQL analysis, runtime query statistics, and data-quality profiling. It is the research implementation for PMIT-6000 at IIT, Jahangirnagar University.

---

- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Status](#status)
- [Prerequisites](#prerequisites)
- [Manual walkthrough](#manual-walkthrough)
  1. [Start the stack](#1-start-the-stack)
  2. [Explore the test applications](#2-explore-the-test-applications)
  3. [Run the static analyzer (Approach B)](#3-run-the-static-analyzer-approach-b)
  4. [Inject the data-quality ground truth](#4-inject-the-data-quality-ground-truth)
  5. [Compare declared and actual schema (RQ6)](#5-compare-declared-and-actual-schema-rq6)
  6. [Watch runtime queries](#6-watch-runtime-queries)
  7. [Load harness, runtime N+1 and collector overhead](#7-load-harness-runtime-n1-and-collector-overhead)
  8. [Profile data quality](#8-profile-data-quality)
  9. [Detect anomalies against a learned baseline](#9-detect-anomalies-against-a-learned-baseline)
  10. [Correlate evidence across layers](#10-correlate-evidence-across-layers)
  11. [Score findings against the ground truth](#11-score-findings-against-the-ground-truth)
  12. [Run the test suites](#12-run-the-test-suites)
- [Resetting](#resetting)

---

## Architecture

DBInsight gathers **evidence** about a Prisma/PostgreSQL application from several independent layers and reports problems as **findings**. Each evidence layer can be switched on or off; comparing configurations is the thesis experiment (M5).

```mermaid
flowchart LR
  subgraph App["Application under analysis"]
    SRC["TypeScript source<br/>(Prisma calls)"]
    DECL["schema.prisma<br/>(declared schema)"]
    DB[("PostgreSQL<br/>(actual schema + data)")]
    COL["packages/collector<br/>Prisma extension +<br/>adapter wrapper"]
  end

  subgraph Core["packages/core · TypeScript · no DB access"]
    PARSE["schema parser"]
    LOC["ORM call location"]
    FLOW["data-flow resolution"]
    RULES["5 static rules"]
    CLI["cli.js<br/>JSON stdin/stdout"]
  end

  subgraph Services["services · Python"]
    BRIDGE["core_bridge"]
    ACT["actual-schema reader"]
    DIV["divergence comparator"]
    GT["ground truth:<br/>manifests · injection · scorer"]
    API["collector service<br/>(FastAPI)"]
    FP["SQL fingerprinting<br/>(SQLGlot AST)"]
    RES[("results DB<br/>runtime.* · experiments.* · dataquality.*")]
    DQ["data-quality profiler<br/>(windowed history ·<br/>referential integrity)"]
    AN["anomaly detector<br/>(z-score · IQR · moving average,<br/>ranges learned from history)"]
    COR["correlation engine<br/>(competing hypotheses,<br/>weighed evidence)"]
    RT["runtime N+1 detector"]
    LOAD["load harness<br/>(fixed seed, ABBA overhead)"]
  end

  DECL --> PARSE --> RULES
  SRC --> LOC --> FLOW --> RULES
  RULES --> CLI
  CLI <-->|subprocess| BRIDGE
  BRIDGE -->|DeclaredSchema| DIV
  DB -->|information_schema, pg_catalog| ACT -->|ActualSchema| DIV
  RULES -->|Findings| GT
  DIV -->|Findings| GT
  COL -->|batched events,<br/>off the request path| API --> FP --> RES
  LOAD -->|HTTP| App
  LOAD -->|requests, CPU/memory samples| RES
  RES --> RT -->|Findings| GT
  DB -->|rows, read-only| DQ -->|profiles: one run per window| RES
  DQ -->|orphan findings| GT
  RES -->|profile history| AN -->|Findings| GT
  RULES -->|static| COR
  RT -->|runtime| COR
  DIV -->|schema| COR
  AN -->|data| COR
  ACT -->|actual schema| COR
  COR -->|"single scored Findings"| GT
```

### Evidence layers

| Layer | Source | Where | Needs a DB | Status |
|---|---|---|---|---|
| Static ORM analysis | application source (ts-morph + type checker) | `packages/core` | no | done (M1) |
| Declared schema | `schema.prisma` | `packages/core` | no | done (M1) |
| Actual schema | `information_schema`, `pg_catalog` | `services/analyzers/schema` | yes | done (M3.1) |
| Runtime | Prisma client extension + driver-adapter wrapper, per-request SQL | `packages/collector`, `services/api`, `services/analyzers/runtime` | yes | done (M3.2–M3.3) |
| SQL | generated SQL (SQLGlot) | `services/analyzers` | yes | planned |
| Data quality | windowed profiles, referential integrity, learned-baseline anomaly detection | `services/analyzers/dataquality`, `services/analyzers/anomaly` | yes | done (M4.1–M4.2) |

**Approach B** = static ORM analysis + declared schema. It runs with no database at all, and it is what the TypeScript core delivers on its own.

### The Finding

Every layer reports in one shape, defined once in [`packages/core/src/models.ts`](packages/core/src/models.ts) and mirrored in Python by [`services/analyzers/finding.py`](services/analyzers/finding.py):

```ts
interface Finding {
  schemaVersion: 1;
  ruleId: string;                 // e.g. "N_PLUS_ONE_IN_LOOP"
  severity: "LOW" | "MEDIUM" | "HIGH";
  confidence: "LOW" | "MEDIUM" | "HIGH";
  file: string; line: number; endLine?: number;
  title: string; body: string;    // body is markdown
  evidence: Evidence[];           // each item names its source layer
  suggestedFix?: string;          // markdown code block, never auto-applied
  fingerprint: string;            // stable across runs; never uses line numbers
}
```

### Rules that shape the design

- **The static core is pure and portable.** `packages/core` is extracted into a standalone tool after the thesis. Rules are pure functions `(AnalysisContext) => Finding[]`: no I/O, no AST access, no database. The analyzer's only input is `{ sourceDir, schemaPath }`, and nothing in it refers to the test applications.
- **Python never reimplements static analysis.** It calls the core as a subprocess through [`packages/core/src/cli.ts`](packages/core/src/cli.ts):
  ```bash
  echo '{"command":"parseSchema","schemaPath":"apps/blog/prisma/schema.prisma"}' | node packages/core/dist/cli.js
  ```
- **Declared and actual schema are never merged.** `DeclaredSchema` (schema.prisma) and `ActualSchema` (the live database) are separate types; the divergence between them is what RQ6 measures.
- **Runtime capture never blocks a request.** The collector buffers events and ships them in the background; if the collector service is down, requests still succeed and events are counted as dropped. With `DBINSIGHT_COLLECTOR_URL` unset it adds no hook at all.
- **Results come only from the scorer.** TP/FP/FN are computed by one module, [`services/experiments/groundtruth/scorer.py`](services/experiments/groundtruth/scorer.py). Nothing counts by hand.

See [CLAUDE.md](CLAUDE.md) for the full list of constraints.

## Repository layout

```
packages/core/            TypeScript static analysis core (extracted after the thesis)
  src/schema/             schema.prisma lexer + parser -> SchemaModel
  src/analyze/            ORM call location, data-flow, await grouping (ts-morph)
  src/rules/              the five rules, pure functions
  src/cli.ts              JSON stdin/stdout entry for the Python services
packages/cli/             product CLI (post-defense)
packages/collector/       runtime collector: Prisma extension + adapter wrapper (thesis only)
services/                 Python 3.12, uv
  analyzers/finding.py    Finding contract (Python mirror)
  analyzers/core_bridge.py  calls packages/core as a subprocess
  analyzers/schema/       declared + actual schema, divergence comparator
  analyzers/sql/          query fingerprinting (SQLGlot AST normalization)
  analyzers/runtime/      runtime N+1 detection over collected requests
  analyzers/dataquality/  data-quality profiler: windowed history, referential integrity
  analyzers/anomaly/      interpretable detectors (z-score, IQR, moving average), no fixed thresholds
  analyzers/correlate/    correlation engine: layers' findings -> single scored findings
  api/                    collector service (FastAPI) + runtime event storage
  experiments/groundtruth/  manifests, data-quality injection, scorer
  experiments/load/       load harness: fixed sequences, repeatability, collector overhead
apps/ecommerce/           test application 1 (Next.js + Prisma + Postgres)
apps/blog/                test application 2
fixtures/                 synthetic inputs for analyzer tests; recorded Prisma SQL
docker/postgres/init/     creates the ecommerce and blog databases
```

## Status

| Milestone | Scope | State |
|---|---|---|
| M0 | Monorepo, test apps, CI | done |
| M1 | Schema parser, ORM call location, data-flow, 5 rules, zero-finding baseline | done |
| M2 | Ground truth: 30 performance, 12 data-quality, 4 divergence problems; scorer | done |
| M3.1 | Actual-schema reader + divergence comparator | done |
| M3.2 | Runtime collector, collector service, AST query fingerprinting | done |
| M3.3 | Load harness, runtime N+1 detection, collector overhead (RQ5) | done |
| M3.4 | M3 exit check | done |
| M4.1 | Data-quality profiler: windowed history, referential integrity | done |
| M4.2 | Anomaly detectors with ranges learned from each column's own history | done |
| M4.3 | Correlation engine: competing hypotheses, corroboration and contradiction, reproducible scores | done |
| M4.4 | M4 exit check | next |
| M5–M8 | Ablation, real-world validation, dashboard, AI explanation layer | planned |

Static rules implemented in the core:

| Rule | Severity | Fires on |
|---|---|---|
| `N_PLUS_ONE_IN_LOOP` | HIGH | Prisma call in a loop (HIGH confidence when the loop iterates an ORM result) |
| `MISSING_INDEX_ON_FILTERED_FIELD` | HIGH | non-unique query whose filtered columns lead no declared index |
| `UNBOUNDED_MUTATION` | HIGH | `deleteMany` / `updateMany` with no `where` |
| `SEQUENTIAL_INDEPENDENT_AWAITS` | MEDIUM | adjacent awaited reads with no data dependency |
| `MISSING_PAGINATION` | MEDIUM | `findMany` with no `take` / `skip` / `cursor` |

## Prerequisites

- Docker with Compose
- Node.js 22+ and pnpm 10 (`corepack enable`)
- Python 3.12 and [uv](https://docs.astral.sh/uv/) (`brew install uv`, or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

```bash
pnpm install
pnpm --filter @dbinsight/core build     # needed by the Python services
cd services && uv sync && cd ..
```

## Manual walkthrough

All commands run from the repository root unless a step says otherwise.

### 1. Start the stack

```bash
docker compose up --build -d
docker compose logs -f ecommerce blog    # wait for "Ready in"; Ctrl-C to stop following
```

This starts PostgreSQL 16, both test apps and the collector service (http://localhost:8700). On first start each app applies its Prisma migrations and seeds deterministic data:

| App | URL | Seed |
|---|---|---|
| ecommerce | http://localhost:3001 | 24 categories, 3,000 customers, 5,000 products, 20,000 orders, 49,850 order items, 15,000 reviews |
| blog | http://localhost:3002 | 150 authors, 40 tags, 2,000 posts, 15,000 comments |

The database is now in the **clean** state: the M2 performance problems are in the code, but the data-quality problems are not yet applied (step 4).

### 2. Explore the test applications

Each app's home page lists its original endpoints. A few to try:

```bash
curl -s "localhost:3001/api/products?limit=2" | jq
curl -s "localhost:3001/api/products/search?q=chair" | jq '.items[0]'
curl -s "localhost:3002/api/posts?tag=postgresql&limit=2" | jq '.items[].title'
curl -s "localhost:3002/api/stats" | jq
```

The injected performance problems each live behind their own endpoint, listed with file and line in the manifests ([ecommerce](services/experiments/groundtruth/manifests/ecommerce.json), [blog](services/experiments/groundtruth/manifests/blog.json)). For example:

```bash
curl -s localhost:3001/api/orders/recent | jq '.items | length'   # N+1: one customer query per order
curl -s localhost:3001/api/products/export | head -3              # unpaginated findMany over 5k rows
curl -s "localhost:3002/api/comments/recent" | jq '.items | length'  # filter on an unindexed column
```

To see the query cost behind a missing-index problem:

```bash
docker compose exec postgres psql -U dbinsight -d ecommerce \
  -c "EXPLAIN ANALYZE SELECT count(*) FROM \"Order\" WHERE status = 'PENDING'"
# -> Seq Scan on "Order" ... Rows Removed by Filter: ~19,800
```

### 3. Run the static analyzer (Approach B)

No database involved. Through the JSON contract:

```bash
pnpm --filter @dbinsight/core build
echo '{"command":"analyze","sourceDir":"apps/ecommerce","schemaPath":"apps/ecommerce/prisma/schema.prisma"}' \
  | node packages/core/dist/cli.js | jq '.result[] | {ruleId, confidence, file, line, title}'
```

Or from TypeScript:

```ts
import { analyze } from "@dbinsight/core";
const findings = await analyze({ sourceDir: "apps/blog", schemaPath: "apps/blog/prisma/schema.prisma" });
```

On the clean pre-M2 apps this produced zero findings (the M1 baseline). On the current, injected apps it reports the performance problems it has rules for.

### 4. Inject the data-quality ground truth

Data-quality problems are applied **after** the clean seed, so that clean data can be profiled first (M4 learns baselines from it). The injection is idempotent SQL in [`services/experiments/groundtruth/inject/`](services/experiments/groundtruth/inject/):

```bash
cd services
uv run python -m experiments.groundtruth.inject ecommerce --dry-run | less   # read it first
uv run python -m experiments.groundtruth.inject ecommerce
uv run python -m experiments.groundtruth.inject blog
cd ..
```

Every problem is confined to the last 30 days of seed time (from 2026-08-02), so it deviates from the column's own history. Check one:

```bash
docker compose exec postgres psql -U dbinsight -d ecommerce -c "
  SELECT created_before_window, round(100.0 * avg((phone IS NULL)::int), 1) AS null_pct
  FROM (SELECT phone, \"createdAt\" < '2026-08-02' AS created_before_window FROM \"Customer\") c
  GROUP BY 1"
# history ~4% NULL, last 30 days ~63% NULL
```

Orphaned rows (possible because a migration dropped three foreign keys):

```bash
docker compose exec postgres psql -U dbinsight -d ecommerce -c "
  SELECT count(*) FROM \"OrderItem\" i WHERE NOT EXISTS (SELECT 1 FROM \"Order\" o WHERE o.id = i.\"orderId\")"
```

### 5. Compare declared and actual schema (RQ6)

The M2 migrations include two hand-written index changes per app that schema.prisma does not reflect. The comparator finds them:

```bash
cd services
uv run python -m analyzers.schema \
  --schema ../apps/ecommerce/prisma/schema.prisma \
  --database-url postgresql://dbinsight:dbinsight@localhost:5432/ecommerce
```

Output (abridged):

```json
{
  "indexes_not_declared":         [{ "table": "Customer", "columns": ["lower(email)"], "index_name": "Customer_email_lower_idx", "...": "..." }],
  "declared_indexes_not_applied": [{ "table": "Product",  "columns": ["createdAt"], "...": "..." }],
  "column_mismatches": [],
  "foreign_keys_not_applied": [
    { "table": "Order",     "columns": ["customerId"], "referenced_table": "Customer" },
    { "table": "OrderItem", "columns": ["orderId"],    "referenced_table": "Order" },
    { "table": "OrderItem", "columns": ["productId"],  "referenced_table": "Product" }
  ]
}
```

Other formats: `--format findings` (a `Finding[]`, the scorer's input) and `--format actual` (the raw `ActualSchema`). The connection is read-only.

### 6. Watch runtime queries

Both apps create their Prisma client through the collector ([`apps/*/src/lib/prisma.ts`](apps/ecommerce/src/lib/prisma.ts)): every operation is recorded with its route, a per-request id, duration, rows returned and the exact SQL Prisma sent (never parameter values). Events are batched to the collector service, which fingerprints each statement and stores it.

```bash
curl -s localhost:3001/api/orders/recent > /dev/null          # an injected N+1
curl -s "localhost:8700/v1/operations?app=ecommerce&limit=3" | jq '.[0] | {route, requestId, model, operation, durationMs, statements: [.statements[] | {fingerprint, sql}]}'
```

Per-request repetition of one query shape, straight from the results database:

```bash
docker compose exec postgres psql -U dbinsight -d dbinsight -c "
  SELECT o.route, o.request_id, s.fingerprint, count(*) AS executions
  FROM runtime.operation o JOIN runtime.statement s USING (operation_id)
  GROUP BY 1, 2, 3 HAVING count(*) > 1 ORDER BY executions DESC LIMIT 5"
# /api/orders/recent executes one customer-lookup shape 20 times per request
```

**Fingerprinting** collapses literal values *and* list arity, so `IN ($1)`, `IN ($1,…,$5)` and `IN ($1,…,$50)` are one shape. pg_stat_statements-style normalization would count them as three and under-count repetition:

```bash
cd services
uv run python -c "
from analyzers.sql import fingerprint, naive_normalize
a = 'SELECT * FROM \"Product\" WHERE \"id\" IN (\$1)'
b = 'SELECT * FROM \"Product\" WHERE \"id\" IN (\$1,\$2,\$3,\$4,\$5)'
print(fingerprint(a).id == fingerprint(b).id, naive_normalize(a) == naive_normalize(b))"
# True False
cd ..
```

Switching collection off (for the overhead comparison in M3.3):

```bash
DBINSIGHT_COLLECTOR_URL= docker compose up -d ecommerce blog    # off: no hook in the query path
docker compose up -d ecommerce blog                             # back on
```

### 7. Load harness, runtime N+1 and collector overhead

The harness requests every endpoint recorded in an app's ground-truth manifest. Path parameters are filled from read-only SQL in [`params.json`](services/experiments/load/params.json), picked with a seeded RNG, so a given seed always sends the identical sequence. Requests are sequential over one keep-alive connection. Every request, every run window and every CPU/memory sample is stored raw in the results database (schema `experiments`); aggregation only happens when reporting.

```bash
cd services
uv run python -m experiments.load plan --app ecommerce --repetitions 1 | jq '.[] | {entry_id, path}'   # preview
uv run python -m experiments.load run  --app ecommerce --repetitions 3
```

**Repeatability**: N identical runs, reporting how much the collector's query counts vary (must be under 5%):

```bash
uv run python -m experiments.load repeatability --app ecommerce --runs 5 --repetitions 3 \
  | jq '{session, totals, max_relative_deviation, worst_route_relative_deviation, passes}'
```

**Runtime N+1**: within one request, the same query fingerprint executing more than `--threshold` times (default 2, i.e. 3+ executions; a query run exactly twice is the separate *repeated identical query* problem):

```bash
uv run python -m analyzers.runtime --app ecommerce --session <session-id> > /tmp/runtime.json
jq '.[] | .evidence[0].data | {route, model, operation, maxExecutionsPerRequest, requestsAffected}' /tmp/runtime.json
uv run python -m experiments.groundtruth --manifest experiments/groundtruth/manifests/ecommerce.json \
  --findings /tmp/runtime.json | jq '.perProblemType[] | select(.problemType == "n_plus_one")'
```

Runtime findings have no source line; they carry the route in their evidence and the scorer matches it to the manifest entry's endpoint.

**Collector overhead (RQ5)**: the collector is switched on and off by recreating the app container, in ABBA order (on, off, off, on) so drift over the session cancels. Each block runs an unrecorded warm-up pass, then the measured run. CPU and memory come from the containers' cgroup v2 counters, read immediately before and after each run: the CPU delta is the exact CPU time the run consumed (reported per request), independent of sampling. `docker stats` samples are kept alongside as a coarse time series. Each run is checked afterwards to have really been in the state it claims (`collector_verified`).

```bash
uv run python -m experiments.load overhead --app ecommerce --cycles 2 --repetitions 5 \
  | jq '{session, latency, median_overhead_ms, median_overhead_ratio, cost}'
uv run python -m experiments.load report --session <session-id>     # recompute from the raw rows
cd ..
```

Raw data, for your own analysis:

```bash
docker compose exec postgres psql -U dbinsight -d dbinsight -c "
  SELECT r.collector_enabled, count(*) AS requests, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY q.latency_ms)::numeric, 2) AS median_ms
  FROM experiments.load_request q JOIN experiments.load_run r USING (run_id)
  WHERE NOT r.warmup GROUP BY 1"
```

### 8. Profile data quality

The profiler records, per table and column: row count, NULL count and rate, distinct count, **duplicate rate** (the fraction of non-null values that repeat another), and the frequency of each value for low-cardinality columns. It reads the live database read-only and stores every profile as its own immutable run in the results database (schema `dataquality`), so history accumulates. It applies no thresholds and judges nothing: deciding what is anomalous is M4.2's job, from each column's own history.

**Snapshot** of whole tables, plus referential-integrity checks against the *declared* relations in schema.prisma:

```bash
cd services
uv run python -m analyzers.dataquality profile --app ecommerce --label snapshot \
  --schema ../apps/ecommerce/prisma/schema.prisma
```

**History** comes from time windows over each table's creation-time column (the timestamp that defaults to `CURRENT_TIMESTAMP`, i.e. Prisma's `@default(now())`). Twelve consecutive 30-day windows ending at the end of the seed data, one stored run per window:

```bash
uv run python -m analyzers.dataquality profile --app ecommerce --label demo \
  --windows 12 --window-days 30 --end 2026-09-01
```

Tables with no creation-time column (e.g. order items) cannot be windowed and are listed under `skipped_tables` in the output; the snapshot profile covers them.

Read a column's history. After step 4 (injection) the last window, 2026-08-02 onwards, is the injected one:

```bash
uv run python -m analyzers.dataquality history --app ecommerce --table Customer --column phone --label demo \
  | jq -c '.[] | {window: .window_start[0:10], rows: .row_count, null_rate}'
# ... {"window":"2026-07-03","rows":121,"null_rate":0.04}   {"window":"2026-08-02","rows":120,"null_rate":0.63}

uv run python -m analyzers.dataquality history --app ecommerce --table Review --column rating --label demo --categories \
  | jq -c '.[-2:][] | {window: .window_start[0:10], distribution}'
# rating 1 goes from ~20% of reviews to ~62%
```

The same columns, straight from SQL:

```bash
docker compose exec postgres psql -U dbinsight -d dbinsight -c "
  SELECT r.window_start::date, c.row_count, round(c.null_rate::numeric, 3) AS null_rate
  FROM dataquality.profile_run r JOIN dataquality.column_profile c USING (run_id)
  WHERE r.label = 'demo' AND c.table_name = 'Customer' AND c.column_name = 'phone'
  ORDER BY r.window_start"
```

**Referential integrity**: for each declared relation whose key lives on the model, count child rows whose (fully non-null) key matches no parent. Rows with a NULL key are exempt, as in SQL. Whether the database also *enforces* the constraint is a different question, answered by the schema comparison in step 5:

```bash
uv run python -m analyzers.dataquality integrity --app ecommerce \
  --schema ../apps/ecommerce/prisma/schema.prisma --report \
  | jq -c '.checks[] | {relation: "\(.model).\(.relation)", checked: .checked_rows, orphans: .orphan_rows}'
# Order.customer 339 orphans, OrderItem.order 645, OrderItem.product 309: exactly the injected ones
```

Without `--report` the same command prints `Finding[]` (rule `ORPHANED_FOREIGN_KEY`), which step 11 scores against the manifest.

**A clean baseline** must be profiled from data that never had the problems applied. Step 9 does that without touching the running databases.

Two knobs: `--max-categories N` (default 50) only caps how many distinct values are *stored* per column; statistics are unaffected, and a column whose values are all unique stores no distribution. `--time-column TABLE=COLUMN` names the window column for a table where it cannot be detected.

### 9. Detect anomalies against a learned baseline

Three interpretable detectors, each given a metric's history and the current value:

| Detector | Expected range, learned from the history |
|---|---|
| `zscore` | mean ± k sample standard deviations |
| `iqr` | Tukey's fences, `[Q1 − m·IQR, Q3 + m·IQR]` (robust to outliers in the history) |
| `moving_average` | moving average ± k moving standard deviations over the latest points (follows a drifting level) |

**There are no fixed thresholds.** No range or limit is ever written in terms of the metric: "NULL rate > 10%" cannot be expressed. The bounds are computed from each column's own history, so the same value can be normal for one column and a spike for another. This is tested directly: every verdict is invariant when history and observation are shifted or rescaled together, which no limit on the metric's value could satisfy, and a scan of the source allows only named method parameters. Those are `k = 3` (the 3-sigma convention), `m = 1.5` (Tukey's), the moving-window length (6) and the minimum history (5) below which a detector declines to judge. They set a method's sensitivity, are constructor arguments, and are printed in every finding's evidence.

What is analysed per column: **NULL rate** (every column); **duplicate rate** for near-unique columns; and for columns with few distinct values, whose repeats are normal, the **distribution shift**: the total-variation distance between a window's category shares and the mean of the baseline windows (how much of the mix moved), judged against how far each historical window sits from the others. A finding needs a **majority** of the detectors that could judge (`--vote any|majority|all`), and its confidence rises with agreement. Only *increases* become findings (`NULL_SPIKE`, `DUPLICATE_SPIKE`, `DISTRIBUTION_SHIFT`); decreases stay visible in `--report`.

**1. Seed a clean baseline** next to the running databases. The seed is deterministic, so a fresh database equals the data before injection; nothing is dropped:

```bash
docker compose exec postgres psql -U dbinsight -d postgres -c "CREATE DATABASE ecommerce_clean"
docker compose run --rm --no-deps \
  -e DATABASE_URL=postgresql://dbinsight:dbinsight@postgres:5432/ecommerce_clean \
  ecommerce sh -c "pnpm db:migrate && pnpm db:seed"
```

**2. Profile both**: the clean copy as the baseline series, the live (injected) database as the current one:

```bash
cd services
uv run python -m analyzers.dataquality profile --app ecommerce --label clean-seed \
  --database-url postgresql://dbinsight:dbinsight@localhost:5432/ecommerce_clean \
  --windows 12 --window-days 30 --end 2026-09-01
uv run python -m analyzers.dataquality profile --app ecommerce --label injected \
  --windows 12 --window-days 30 --end 2026-09-01
```

**3. Measure false alarms on the clean history.** A walk-forward backtest judges each window only against the windows before it; on data known to be clean, every alarm is a false alarm:

```bash
uv run python -m analyzers.anomaly backtest --app ecommerce --label clean-seed \
  | jq '{per_detector, vote_result, false_alarms: [.false_alarms[] | {table, column, metric, window_start}]}'
```

**4. Detect** in the latest window of the injected series, using the range learned from the clean one:

```bash
uv run python -m analyzers.anomaly detect --app ecommerce \
  --baseline-label clean-seed --current-label injected > /tmp/anomalies.json
jq -c '.[] | {rule: .ruleId, column: "\(.evidence[0].data.table).\(.evidence[0].data.column)", observation: .evidence[0].data.observation, confidence}' /tmp/anomalies.json
jq '.[0].evidence[] | select(.data.detector) | {detector: .data.detector, expected: [.data.expectedLower, .data.expectedUpper], observation: .data.observation}' /tmp/anomalies.json
```

Each finding carries one piece of evidence per detector: the learned range, the observation, the history size and the parameters used. Score them like any other findings (step 11). `--detectors zscore,iqr` and `--vote` compare configurations; `--report` lists every anomaly including decreases; leaving out `--current-label` judges a series against its own earlier windows.

Two behaviours to know about. A history with no spread (a column that has always been exactly 0) collapses to a single-value range, so any change is flagged; the evidence marks these `degenerate`. And a metric that trends or depends on volume (an order-status mix that depends on order age, a foreign-key duplicate rate that rises with row count) will look anomalous to any method that learns only from its own past; the backtest is how to see which columns do that.

### 10. Correlate evidence across layers

Each layer reports on its own, and they can disagree. The correlation engine joins their findings on what they are about, weighs the evidence, and emits **one finding per problem**, carrying the evidence of every layer that contributed, each item naming its layer.

**Hypotheses compete.** At a *site* (one request route and one model) the engine may hold several explanations for the same symptom. Each is scored from evidence for and against it, in nats of log-odds:

| Evidence | Weight |
|---|---|
| a layer's own confidence in what it raised: HIGH / MEDIUM / LOW | +1.5 / +0.5 / −0.5 |
| runtime saw one query shape repeat within a request (N+1): HIGH / MEDIUM / LOW | +2.5 / +1.5 / +0.5 |
| the *actual* schema has an index leading with the filtered column (contradicts "missing index") | **−4.0** |
| the actual schema has no such index (confirms it) | +1.0 |
| orphaned rows, and the database has no foreign-key constraint (explains them) | +1.5 |
| orphaned rows, yet the database enforces the constraint (should be impossible) | −3.0 |

A hypothesis is believed at log-odds 0 (posterior 0.5) and strongly believed at log 4 (posterior 0.8, HIGH confidence). The weights are expert-set, **not calibrated**: they encode which evidence outweighs which (a real index outweighs even the strongest suspicion drawn from a declaration), they live in one file ([`scoring.py`](services/analyzers/correlate/scoring.py)), and M5's ablation is where to vary them.

**Contradicting evidence can change a finding's type.** The canonical case: static analysis sees an N+1 loop *and*, because schema.prisma declares no index on the filtered column, suspects a missing index; runtime shows the query executing hundreds of times per request; but the database itself has that index (created outside Prisma). The missing-index hypothesis is eliminated, and the result is an N+1 finding, not a missing-index finding. If static analysis had seen only the unindexed filter, the *type* of the finding changes from missing-index to N+1. The eliminated hypothesis is not discarded: its evidence stays on the surviving finding, tagged `ruled_out`.

Every evidence item on an output finding carries `data.correlation = {role, hypothesis, weightNats, posterior}`, with role `supports`, `contradicts`, `ruled_out` or `context`.

Rules implemented: **F1** missing index vs N+1 (static + declared + runtime + actual schema), and **F2** orphaned rows against the actual schema's foreign keys (data + declared + actual; confidence only). Anything without a counterpart in another layer passes through unchanged. Static and runtime findings are recognised as the same request through the Next.js App Router convention (`src/app/api/orders/[id]/route.ts` is `/api/orders/[id]`); a static finding outside a route handler cannot be joined to runtime and is judged by the schema layers alone.

Collect every layer's findings, then correlate (declared schema and the live database supply the schema facts; either may be omitted, and an absent layer has no opinion):

```bash
cd services
echo '{"command":"analyze","sourceDir":"../apps/ecommerce","schemaPath":"../apps/ecommerce/prisma/schema.prisma"}' \
  | node ../packages/core/dist/cli.js | jq '.result' > /tmp/static.json
uv run python -m analyzers.runtime --app ecommerce > /tmp/runtime.json
uv run python -m analyzers.schema --schema ../apps/ecommerce/prisma/schema.prisma \
  --database-url postgresql://dbinsight:dbinsight@localhost:5432/ecommerce --format findings > /tmp/divergence.json
uv run python -m analyzers.anomaly detect --app ecommerce --baseline-label clean-seed --current-label injected > /tmp/anomaly.json
uv run python -m analyzers.dataquality integrity --app ecommerce --schema ../apps/ecommerce/prisma/schema.prisma > /tmp/integrity.json
jq -s 'add' /tmp/static.json /tmp/runtime.json /tmp/divergence.json /tmp/anomaly.json /tmp/integrity.json > /tmp/all-layers.json

uv run python -m analyzers.correlate --findings /tmp/all-layers.json \
  --declared-schema ../apps/ecommerce/prisma/schema.prisma \
  --database-url postgresql://dbinsight:dbinsight@localhost:5432/ecommerce > /tmp/correlated.json
```

See what was decided and why:

```bash
uv run python -m analyzers.correlate --findings /tmp/all-layers.json \
  --declared-schema ../apps/ecommerce/prisma/schema.prisma \
  --database-url postgresql://dbinsight:dbinsight@localhost:5432/ecommerce --report \
  | jq -r '.decisions[] | "\(.site)  ->  " + ([.hypotheses[] | "\(.rule_id) \(.posterior) \(.confidence)"] | join(" | "))'
jq '.[] | select(.ruleId == "N_PLUS_ONE_IN_LOOP") | .evidence[] | {source, role: .data.correlation.role, weight: .data.correlation.weightNats}' /tmp/correlated.json | head -20
```

Compare the layers side by side with the merged result, through the same scorer (step 11):

```bash
for f in all-layers correlated; do
  uv run python -m experiments.groundtruth --manifest experiments/groundtruth/manifests/ecommerce.json \
    --findings /tmp/$f.json | jq -c '{findings: "'$f'", tp: .aggregate.tp, fp: .aggregate.fp, fn: .aggregate.fn, duplicates: .aggregate.duplicates}'
done
```

On the test apps, correlation keeps every true positive, adds no false positive, and turns each N+1 that static analysis and runtime both reported into one HIGH-confidence finding (the scorer's *duplicates* go from 3 to 0 per app). It does not eliminate anything there because neither app contains a declared-only false positive; elimination and type change are exercised by the tests, including one that runs the real TypeScript analyzer against a fixture and reads a real database index.

**Reproducible.** The input is put in a canonical order, weights are combined order-independently, and nothing random or time-dependent is involved: the same findings give byte-identical output across runs, hash seeds and input orders (tested, including across separate processes).

### 11. Score findings against the ground truth

Any `Finding[]`, from any layer, is scored the same way:

```bash
cd services
uv run python -m analyzers.schema --schema ../apps/blog/prisma/schema.prisma \
  --database-url postgresql://dbinsight:dbinsight@localhost:5432/blog --format findings > /tmp/blog-divergence.json
uv run python -m experiments.groundtruth \
  --manifest experiments/groundtruth/manifests/blog.json --findings /tmp/blog-divergence.json \
  | jq '.perProblemType[] | select(.tp + .fp > 0)'
```

And for Approach B (static findings):

```bash
echo '{"command":"analyze","sourceDir":"../apps/blog","schemaPath":"../apps/blog/prisma/schema.prisma"}' \
  | node ../packages/core/dist/cli.js | jq '.result' > /tmp/blog-static.json
uv run python -m experiments.groundtruth \
  --manifest experiments/groundtruth/manifests/blog.json --findings /tmp/blog-static.json | jq '.aggregate'
```

And the orphaned-row findings from the data-quality profiler:

```bash
uv run python -m analyzers.dataquality integrity --app ecommerce \
  --schema ../apps/ecommerce/prisma/schema.prisma > /tmp/ecommerce-orphans.json
uv run python -m experiments.groundtruth \
  --manifest experiments/groundtruth/manifests/ecommerce.json --findings /tmp/ecommerce-orphans.json \
  | jq -c '.perProblemType[] | select(.problemType == "orphaned_foreign_key") | {tp, fp, fn}'
# {"tp":3,"fp":0,"fn":0}
```

And the anomaly findings from step 9:

```bash
uv run python -m experiments.groundtruth \
  --manifest experiments/groundtruth/manifests/ecommerce.json --findings /tmp/anomalies.json \
  | jq -c '.perProblemType[] | select(.problemType | IN("null_spike","duplicate_spike","distribution_shift")) | {problemType, tp, fp, fn}'
```

Matching is by **problem type and location**: code findings must overlap the manifest entry's lines; data and schema findings match on the `table`/`column` named in their evidence; runtime findings match on the `route` in their evidence against the entry's endpoint. See the module docstring of [`scorer.py`](services/experiments/groundtruth/scorer.py) for the exact rules.

### 12. Run the test suites

```bash
pnpm typecheck && pnpm test              # TypeScript: core (parser, ORM location, data-flow, rules, CLI) + collector

cd services
uv run ruff check . && uv run ruff format --check .
uv run pytest                            # unit tests; database tests skip
DBINSIGHT_TEST_DATABASE_URL=postgresql://dbinsight:dbinsight@localhost:5432/dbinsight \
DBINSIGHT_ECOMMERCE_DATABASE_URL=postgresql://dbinsight:dbinsight@localhost:5432/ecommerce \
  uv run pytest                          # + catalog reader, event storage, data-quality profiler,
                                         #   integrity checks and anomaly-series loading on a
                                         #   scratch schema, and a live run
                                         #   that regenerates Prisma IN-list SQL (1/5/50 ids) and
                                         #   checks it collapses to one fingerprint
```

CI (`.github/workflows/ci.yml`) runs both suites on every push, with a Postgres service for the integration tests.

## Resetting

```bash
docker compose down -v      # drop the database volume
docker compose up -d        # fresh migrations + clean seed (no data-quality problems)
```

The seed is deterministic: every reset produces byte-identical data.
