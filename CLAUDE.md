# DBInsight

Research implementation for PMIT-6000 (IIT, Jahangirnagar University). A hybrid
static and runtime analysis framework detecting database performance and
data-quality problems in Prisma/PostgreSQL applications.

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

```
packages/core/          TypeScript static analysis core
packages/cli/           CLI wrapper (post-defense, Phase 0)
services/api/           FastAPI — orchestration
services/analyzers/     Python — SQL, data quality, anomaly, correlation
services/experiments/   Ablation harness, ground-truth scoring
apps/ecommerce/         Test application 1 (Prisma + Postgres)
apps/blog/              Test application 2 (Prisma + Postgres)
apps/dashboard/         Next.js dashboard (M8)
fixtures/               Analyzer test fixtures — synthetic, minimal
```

## Stack

TypeScript: ts-morph, vitest. Python: FastAPI, Pydantic, SQLGlot, pandas,
scipy, pytest. Postgres 16. Docker Compose for everything.

## Research context that constrains design

- Approach B (static source + declared schema) must run with NO database
  connection. Never introduce a DB dependency into anything Approach B uses.
- The declared schema (`schema.prisma`) and the actual schema
  (`information_schema`) are SEPARATE evidence sources and must never be merged
  into one abstraction. Measuring their divergence is RQ6.
- The AI explanation layer consumes findings only. It must be structurally
  incapable of altering type, severity, or confidence.

## The Finding model

```typescript
interface Finding {
  schemaVersion: 1;
  ruleId: string;              // "N_PLUS_ONE_IN_LOOP"
  severity: "LOW" | "MEDIUM" | "HIGH";
  confidence: "LOW" | "MEDIUM" | "HIGH";
  file: string;                // repo-relative
  line: number;
  endLine?: number;
  title: string;
  body: string;                // markdown
  evidence: Evidence[];
  suggestedFix?: string;       // markdown code block, never auto-applied
  fingerprint: string;         // stable across runs; dedupe key
}
```

## Rules implemented

| ID | Severity | Fires on |
|---|---|---|
| `N_PLUS_ONE_IN_LOOP` | HIGH | Prisma call in a loop over an ORM result |
| `MISSING_INDEX_ON_FILTERED_FIELD` | HIGH | Filtered field with no declared index |
| `UNBOUNDED_MUTATION` | HIGH | `deleteMany`/`updateMany` with no `where` |
| `SEQUENTIAL_INDEPENDENT_AWAITS` | MEDIUM | Independent awaited calls, no `Promise.all` |
| `MISSING_PAGINATION` | MEDIUM | `findMany` with no `take`/`skip`/`cursor` |

## Conventions

- Conventional commits.
- Every rule ships with fixture tests: one true positive, one near-miss that
  must NOT fire.
- No new dependency without justification in the PR description.
- When unsure whether something belongs in core or services, ask rather than
  guess — the boundary is load-bearing.
