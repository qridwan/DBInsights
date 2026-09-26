# Running the DBInsight dashboard

A complete guide from a fresh checkout to a working dashboard. About 15 minutes the first time,
most of it waiting for Docker images and the first compile.

## What you are starting

Four things, plus one optional:

| Piece | What it does | Where | Port |
|---|---|---|---|
| Docker stack | PostgreSQL 16, the two test apps (`ecommerce`, `blog`), the runtime collector | Docker | 5432, 3001, 3002, 8700 |
| Dashboard API | Runs scans, stores findings, serves them read-only | your machine (Python) | 8710 |
| Dashboard | The Next.js web UI you look at | your machine (Node) | 3003 |
| AI explanations (optional) | Turns a finding's evidence into a written explanation | inside the dashboard API | n/a |

The dashboard API runs on your machine, not in Docker, because a scan needs `node`, the repository
source and the analyzer build.

```
browser :3003 --> Next.js dashboard --> dashboard API :8710 --> Postgres :5432
                                              |--> runs the analyzer (node), reads apps/*
                                              |--> triggers load against the apps :3001/:3002
                                                    which report to the collector :8700
```

## 1. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Docker with Compose | recent, **running** | `docker compose version` |
| Node.js | 22 or newer | `node --version` |
| pnpm | 10 | `pnpm --version` (`corepack enable` if missing) |
| Python | **3.12 or newer** | see step 3 |
| git | any | |

macOS's built-in Python is 3.9 and will not work: the code uses `str | None` syntax. You will see
`TypeError: unsupported operand type(s) for |` if you use it.

## 2. Install JavaScript dependencies and build the analyzer

From the repository root:

```bash
pnpm install
pnpm --filter @dbinsight/core build
```

The build produces `packages/core/dist/cli.js`, which the Python services call to run static
analysis. If it is missing, scans fail with "not found; build it".

## 3. Set up Python

Pick one option.

### Option A: uv (recommended)

```bash
brew install uv          # or: curl -LsSf https://astral.sh/uv/install.sh | sh
cd services
uv sync
```

uv downloads the pinned Python 3.12 itself. Every Python command below is written as `uv run ...`.

### Option B: a plain virtual environment

```bash
brew install python@3.12
cd services
/opt/homebrew/bin/python3.12 -m venv .venv          # Intel Macs: /usr/local/bin/python3.12
.venv/bin/python --version                          # must say 3.12 or newer
source .venv/bin/activate
pip install "fastapi>=0.115" "psycopg[binary]>=3.2" "pydantic>=2.7" "sqlglot>=26" \
            "uvicorn>=0.30" "scipy>=1.13" "matplotlib>=3.9"
```

With the environment activated, drop the `uv run` prefix from every Python command below. If a
previous attempt created `.venv` with the wrong Python, delete it first: `rm -rf .venv`.

## 4. Start the Docker stack

From the repository root:

```bash
docker compose up --build -d
docker compose ps
```

All four services (`postgres`, `ecommerce`, `blog`, `collector`) should be `running`. On first start
each app applies its Prisma migrations and loads deterministic seed data, which takes a minute or two.
Wait until both apps answer:

```bash
curl -s -o /dev/null -w "ecommerce %{http_code}\n" localhost:3001
curl -s -o /dev/null -w "blog %{http_code}\n" localhost:3002
curl -s localhost:8700/health
```

Expect `200`, `200` and `{"status":"ok"}`. Watch startup with `docker compose logs -f ecommerce blog`
(look for "Ready in").

Default credentials and ports come from `.env.example`. You only need a `.env` if you want to
change them.

## 5. One-time setup: problems and baseline

Scans compare the live data against a learned baseline, and the demo needs known problems present.
This step prepares both, and is safe to repeat (it never drops anything):

```bash
cd services
uv run python -m experiments.ablation setup
```

It does four things: injects the ground-truth data problems into each app database, creates a
never-injected copy (`ecommerce_clean`, `blog_clean`), profiles that copy over 12 windows of 30
days as the baseline, and makes sure the core is built.

Success looks like:

```
ecommerce: ground-truth problems injected (idempotent)
ecommerce: baseline 'ablation-baseline' profiled over 12 windows of 30 days
blog: ground-truth problems injected (idempotent)
blog: baseline 'ablation-baseline' profiled over 12 windows of 30 days
```

Skipping this makes scans fail on the data layer with
`no baseline profiles labelled 'ablation-baseline'`.

## 6. Start the dashboard API

In a **new terminal**, from `services/`:

```bash
cd services
DBINSIGHT_RESULTS_DATABASE_URL=postgresql://dbinsight:dbinsight@localhost:5432/dbinsight \
  uv run uvicorn api.dashboard.app:app --port 8710
```

Leave it running. Check it from another terminal:

```bash
curl -s localhost:8710/health           # {"status":"ok"}
curl -s localhost:8710/v1/apps          # ecommerce and blog, with their latest scan
```

The first request creates its tables (`dashboard` schema) in the results database.

## 7. Start the dashboard

In another **new terminal**, from the repository root:

```bash
pnpm --filter dashboard dev
```

The first page load compiles the app and takes about 15 seconds. Then open
**http://localhost:3003**.

If the API is somewhere other than `localhost:8710`, set `DBINSIGHT_API_URL` before starting.

## 8. Use it

1. Choose **ecommerce** on the home page.
2. Press **Run scan** (top right). It takes about 10 seconds: every evidence layer runs, and the
   runtime layer drives real traffic at the app. The page then shows the new scan.
3. The five tabs, all describing the same scan:

| Tab | What it shows |
|---|---|
| Health | Findings by severity per scan (a trend once you have run several scans), by contributing layer, layer timings |
| Findings | Filter by severity, confidence, rule and evidence layer |
| Query analytics | Which endpoints repeat the same query most within one request, the most frequent and slowest query shapes |
| Data quality | Each column's current value against the range learned from its own history; a red dot is outside it |
| Schema divergence | Declared schema (`schema.prisma`) and actual database catalog side by side, never merged, with indexes present in only one highlighted |

### Demo: an N+1 problem end to end, under five minutes

1. Run a scan on `ecommerce` (step 2 above).
2. **Findings**, filter rule `N_PLUS_ONE_IN_LOOP`, open the first finding.
3. Read its **evidence chain**. Each item is labelled with the layer that produced it:
   - **Static source**: a query runs inside a loop over the result of an earlier query.
   - **Runtime**: 24 executions of the same query shape in one request to `/api/categories/overview`.
   - **SQL**: the normalised query shape.
   - **Actual schema**: the index that makes each execution cheap, so the cost is their number.
   The header shows "4 of 6 layers contributed" and greys out the layers that added nothing.
4. **Query analytics** shows the same endpoint at the top of "Most repeated within one request".
5. Run more scans to see the health trend fill in.

### Scan a project of your own (real-world project)

The home page has a **Scan a project** form under "Scanned projects". Give it either:

- **Git URL**: an `https://host/owner/repository` address (public repositories; only plain https is accepted).
  It is cloned shallowly into `services/experiments/realworld/work/projects/`.
- **Local folder**: an absolute path on the machine running the dashboard API.

Optionally set the **schema path** (default: the `schema.prisma` with the most models, skipping
`node_modules`) and a **name**. Press **Scan project**. A small repository takes seconds; a large
one, or a slow disk, can take a minute or more, and cloning adds to that.

A scanned project is analysed **without a database**: static ORM analysis, SQL text in the
repository, and the declared schema (`schema.prisma`). It has three tabs (Health, Findings, Schema
divergence) and shows the declared schema only. Query analytics and Data quality are hidden,
because they need a running application and its database. "Scan again" re-runs it (a Git project is
updated first).

What to watch for:

- **A red banner "The analyzer found no Prisma operations in this project."** means it loaded the
  source and recognised no Prisma calls, so **zero findings is not evidence of clean code**. In the
  real-world study this happened for projects that import their client from another workspace
  package, extend `PrismaClient` (NestJS), or wrap it in a factory.
- **Findings in test files** are reported like any other; the analyzer does not tell test code from
  application code.
- **Dependencies are not installed** and nothing from the project is executed, so results reflect the
  source alone. (Installing would run code from the repository.)
- The health page notes which layers ran and, for the evidence chain on a finding, which were "not run".
- Project names cannot be `ecommerce` or `blog`.

**Restart the API after updating.** The dashboard API has no auto-reload, so an API started before
this feature was added does not have the project endpoints; stop it (Ctrl-C) and start it again
(step 6). The web app reloads by itself.

## 9. Optional: AI explanations

Without this, the "Explain this finding" button on a finding page says the layer is not configured.
The explanation is written from the evidence only and cannot change the finding's severity or
confidence.

Install the extra and restart the API (step 6) with a key in its environment:

```bash
cd services
uv sync --extra explain                      # Option B: pip install "anthropic>=0.40"
ANTHROPIC_API_KEY=sk-ant-... \
DBINSIGHT_RESULTS_DATABASE_URL=postgresql://dbinsight:dbinsight@localhost:5432/dbinsight \
  uv run uvicorn api.dashboard.app:app --port 8710
```

The model defaults to `claude-sonnet-5`; override with `DBINSIGHT_EXPLAIN_MODEL`. Explanations are
cached in Postgres by rule and evidence, so identical findings do not trigger repeated calls. This
path has been tested with a fake model; the first real call is worth watching.

## 10. Stopping and resetting

Stop the API and dashboard with Ctrl-C in their terminals. Then:

```bash
docker compose stop            # keep the data
docker compose down            # remove containers, keep the database volume
docker compose down -v         # also delete the database: a full reset
```

After `down -v`, repeat steps 4 and 5 (the stack recreates seed data; setup re-injects the problems
and rebuilds the baseline). Old scans are stored in the database, so they are gone too.

## 11. Ports

| Port | Service |
|---|---|
| 3001 | ecommerce test app |
| 3002 | blog test app |
| 3003 | dashboard |
| 5432 | PostgreSQL |
| 8700 | runtime collector |
| 8710 | dashboard API |

If one is taken, stop what is using it (`lsof -iTCP:3003 -sTCP:LISTEN`) or change the app ports in
`.env`.

## 12. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `zsh: command not found: uv` | uv is not installed. `brew install uv`, or use Option B in step 3. |
| `TypeError: unsupported operand type(s) for \|` | The virtual environment uses Python 3.9. Recreate it with 3.12+ (step 3, Option B). |
| Dashboard shows "Cannot reach the dashboard API" | The API (step 6) is not running, or `DBINSIGHT_API_URL` is wrong. The page prints the command to start it. |
| `KeyError: DBINSIGHT_RESULTS_DATABASE_URL` when starting the API | The variable was not set on the same command line. Include it exactly as in step 6. |
| Run scan fails: `no baseline profiles labelled 'ablation-baseline'` | Run the one-time setup (step 5). |
| Run scan fails: `the collector is switched off` or no runtime operations | The app containers or collector are not running, or were started without the collector. `docker compose up -d`, then `docker compose ps`. |
| Run scan fails: `... not found; build it with pnpm` | Build the core: `pnpm --filter @dbinsight/core build`. |
| Run scan returns 409 | A scan is already running. Wait for it to finish; only one runs at a time. |
| `connection refused` on 5432 | Docker is not running, or Postgres is still starting. `docker compose ps`. |
| Dashboard page blank for 15 to 20 seconds on first load | First compile of each route. Later loads are fast. |
| Charts empty for a moment after load | They draw once the page finishes loading; wait a second. |
| Scanning a project fails with "the Git URL must look like https://host/owner/repository" | Only plain https URLs are accepted (no `git@`, `ssh://`, `file://` or `http://`). |
| Scanning a project fails with "is not a directory" | The path must exist on the machine running the API, as an absolute path. |
| "Scan project" gives 404 or "Not Found" | The API is an older process without the project endpoints. Restart it (step 6). |
| Scan project stays on "Cloning and scanning..." for minutes | A large repository or a slow disk. It is not a hang; the analyzer reads every source file. Wait, or check `docker`/disk load. |
| A scanned project shows 0 findings and a red banner | The analyzer located no Prisma operations (see "Scan a project of your own"). The result says nothing about the code's quality. |
| Everything worked, then a scan shows odd data-quality numbers | The databases changed since setup. Repeat step 5; it is safe to re-run. |

## 13. Quick reference: every command in order

```bash
# once
pnpm install
pnpm --filter @dbinsight/core build
cd services && uv sync && cd ..
docker compose up --build -d
cd services && uv run python -m experiments.ablation setup && cd ..

# every time (two terminals)
cd services && DBINSIGHT_RESULTS_DATABASE_URL=postgresql://dbinsight:dbinsight@localhost:5432/dbinsight \
  uv run uvicorn api.dashboard.app:app --port 8710
pnpm --filter dashboard dev        # then open http://localhost:3003
```

For a faster, production-style frontend: `pnpm --filter dashboard build && pnpm --filter dashboard start`.
