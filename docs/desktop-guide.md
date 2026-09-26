# DBInsight desktop app (Tauri)

A native app for the dashboard: one icon to open, one window to use. It is built with
[Tauri 2](https://tauri.app/start/), so it uses the operating system's own web view (small, and it
behaves like a native app) rather than bundling a browser.

## What it is, and what it is not

The dashboard is a Next.js web app that talks to a Python API and PostgreSQL. Those cannot be flattened
into a single static file, so the desktop app is a **native shell that runs the whole stack for you**:

| The app does | How |
|---|---|
| Starts what is not running | PostgreSQL and the mail inbox through Docker Compose, then the analysis API, then the dashboard |
| Reuses what already is | Anything already listening on its port is used as it is and left running when you quit |
| Shows progress | A native splash screen with a step for each service, and the log if one fails |
| Opens the dashboard | In a native window, with the usual Mac menus, remembered window size, and one instance at a time |
| Stops what it started | When you quit, and only that |
| Picks folders natively | **Scan a project > Local folder > Browse...** opens the operating system's own folder dialog |
| Keeps links safe | A link to another website opens in your normal browser, never inside the app |

It is **not** a self-contained installer: it still needs a DBInsight checkout on the machine (the API scans
the projects and runs the analyzer from it), Docker for PostgreSQL, and the Python environment from the
[dashboard guide](dashboard-guide.md). The first time you open the app it asks which folder holds your
checkout, and remembers it.

## Prerequisites

Everything in the [dashboard guide](dashboard-guide.md) (Docker, Node 22+, pnpm, the Python environment),
plus the Rust toolchain to build the app:

```bash
# Rust, installed without touching your shell profile (remove any time with `rustup self uninstall`):
curl -sSf -o /tmp/rustup-init https://static.rust-lang.org/rustup/dist/aarch64-apple-darwin/rustup-init
chmod +x /tmp/rustup-init && /tmp/rustup-init -y --no-modify-path --profile minimal
export PATH="$HOME/.cargo/bin:$PATH"     # add this to your profile to keep it
```

On an Intel Mac use `x86_64-apple-darwin` in the URL. macOS also needs the Xcode command line tools
(`xcode-select --install`). Linux and Windows have their own system libraries: see
https://tauri.app/start/prerequisites/. The service launcher is written for macOS and Linux; Windows would
need its commands adapted.

## Run it while developing

From the repository root:

```bash
pnpm install
pnpm --filter desktop tauri dev
```

The first build compiles the Tauri dependencies (a few minutes); later runs take seconds. A window opens
with the splash screen, starts anything that is not running, and then shows the dashboard. In this mode the
dashboard runs with `next dev`, so your edits to `apps/dashboard` appear immediately.

## Build the app

```bash
pnpm --filter desktop tauri build
```

This produces `DBInsight.app` and a `.dmg` under `apps/desktop/src-tauri/target/release/bundle/`. Drag the
app to Applications and open it. In this build the dashboard is built once on first launch (about a minute,
shown on the splash screen) and then run in production mode.

## First launch

1. Open DBInsight. If it cannot find your checkout it says **Where is DBInsight?**: choose the folder that
   contains `apps`, `services` and `packages`.
2. Watch the three steps turn green. If Docker is not running, start Docker Desktop and press **Try again**.
3. The dashboard opens. Create an account (the first account is the administrator) and read the code from
   the email inbox: **Help > Open the Email Inbox**.

## Menus

| Menu | Items |
|---|---|
| DBInsight | About, **Change DBInsight Folder...**, Hide, Quit |
| Edit | Undo, Redo, Cut, Copy, Paste, Select All (so text fields behave normally) |
| View | Reload (Cmd+R), Back (Cmd+[), Forward (Cmd+]), Full Screen |
| Window | Minimize, Zoom, Close |
| Help | Open the Email Inbox (Mailpit, for verification codes), Show the Logs Folder, **Restart Services** |

## Where things are

| | Location (macOS) |
|---|---|
| Settings | `~/Library/Application Support/edu.juniv.dbinsight/config.json` (your folder, ports, database URL) |
| Logs | `~/Library/Logs/edu.juniv.dbinsight/`: `desktop.log` (what the app did), `api.log`, `dashboard.log`, `docker.log` |

`config.json` fields: `home`, `api_port` (8710), `dashboard_port` (3003), `database_port` (5432),
`database_url`, `dev_server` (run the dashboard with `next dev`; true in development builds).

## How it works

```
                 native window (Tauri, the OS web view)
                  |                                  \
   splash screen (local page)                 the dashboard (http://localhost:3003)
   invokes: start_services, read_log ...      may call ONE native thing: the folder dialog
                  |
   Rust: checks ports, starts docker / uvicorn / next as child processes
         (each in its own process group), waits for health, logs everything
```

- The splash screen is a small static page. It calls the app's own commands (start, logs, choose folder).
- The dashboard is the normal Next.js app, reached over `http://localhost:3003`. Tauri's permission system
  (`src-tauri/capabilities/`) lets that page use exactly one native feature, the folder dialog. It cannot call
  the app's commands, so a bug in the dashboard cannot be used to change your settings or stop services.
- The window only ever shows its own pages and the dashboard's address. Any other link opens in your browser.
- The desktop app sets `DBINSIGHT_COOKIE_SECURE=0` for the dashboard: the sign-in cookie is normally marked
  `Secure`, which a web view does not keep over `http://localhost`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Docker could not start PostgreSQL" | Start Docker Desktop, then **Try again**. The **Show details** button prints `docker.log` |
| "The API did not start" | Open `api.log`. Usually the Python environment is missing: follow the dashboard guide (`services/.venv` with the dependencies installed, or `uv`) |
| "The dashboard did not start" | Open `dashboard.log`. On a first release launch it builds the dashboard first; if that fails, run `pnpm --filter dashboard build` in a terminal to see why |
| It asks for the folder every time | It could not save `config.json`, or the folder moved. Choose it again with **DBInsight > Change DBInsight Folder...** |
| `node`, `pnpm` or `docker` "not found" | A Mac app started from Finder has a minimal PATH. The app adds Homebrew, nvm, Volta and pnpm locations and reads your login profile; if yours lives elsewhere, set `DBINSIGHT_HOME` and put the tools in `/opt/homebrew/bin` or `/usr/local/bin` |
| Opening `http://127.0.0.1:1430` in a browser shows a page that does nothing | That is the splash page served by `tauri dev`. It only works inside the native DBInsight window, which is the one that starts the services. Use the window that opens, not a browser |
| A second window will not open | By design: only one instance runs (two would fight over the same ports). Launching again brings the first one forward |
| The window is blank after Restart Services | Wait for the splash: it starts everything again and reopens the dashboard when it is ready |

## What was and was not tested

**Verified**

- Rust unit tests (`cargo test`, 16 pass): configuration and folder discovery, health checks, log reading,
  which addresses the window may show, that stopping a service ends every process it started, and the
  permission boundary (the dashboard page is granted only the folder dialog; every app command is declared
  and granted to the splash screen only).
- The debug binary was launched against the already-running stack. `desktop.log` recorded: splash loaded,
  database / API / dashboard detected as ready, then the window navigating to `http://localhost:3003/login`.

**Not verified**

- Starting the services from cold (Docker, uvicorn, `next` spawned by the app). Only the "already running"
  path was exercised, to avoid disturbing a live stack.
- `pnpm --filter desktop tauri build` (the `.app` / `.dmg` bundle).
- How the splash screen and the native folder dialog look, and whether `window.__TAURI__` reaches the
  remote dashboard page: a native window cannot be screenshotted from the automated environment.
- One earlier run of a debug binary built before logging existed exited by itself after about 20 s. The
  rebuilt binary ran 40 s without exiting, but the cause was not established.
