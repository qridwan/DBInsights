//! Starts, watches and stops the three things the dashboard needs: PostgreSQL (through Docker
//! Compose), the analysis API, and the dashboard web server. Anything already running is used as
//! it is and left running when the app quits; only what this app started is stopped.

use crate::config::{validate_home, Config};
use std::fs::OpenOptions;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

pub type Emit<'a> = &'a dyn Fn(&str, &str, &str);

#[derive(Default)]
pub struct Services {
    children: Mutex<Vec<(String, Child)>>,
}

// ---- probing ------------------------------------------------------------------------------

pub fn tcp_open(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&address, Duration::from_millis(400)).is_ok()
}

/// The HTTP status of `GET path` on localhost, or None if nothing answers. Plain HTTP/1.0 over a
/// socket: enough for a health check without pulling in an HTTP client.
pub fn http_status(port: u16, path: &str) -> Option<u16> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_millis(600)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(3))).ok()?;
    stream.set_write_timeout(Some(Duration::from_secs(3))).ok()?;
    write!(stream, "GET {path} HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n").ok()?;
    let mut head = [0u8; 64];
    let n = stream.read(&mut head).ok()?;
    parse_status(&String::from_utf8_lossy(&head[..n]))
}

pub fn parse_status(response: &str) -> Option<u16> {
    let line = response.lines().next()?;
    let mut parts = line.split_whitespace();
    if !parts.next()?.starts_with("HTTP/") {
        return None;
    }
    parts.next()?.parse().ok()
}

pub fn wait_until(timeout: Duration, mut ready: impl FnMut() -> bool) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if ready() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    ready()
}

// ---- running commands ---------------------------------------------------------------------

/// A macOS app started from Finder has almost no PATH. Add the places node, pnpm, uv and docker
/// normally live, so the commands below are found without the user's shell configuration.
pub fn augmented_path() -> String {
    let home = std::env::var("HOME").unwrap_or_default();
    let mut dirs: Vec<String> = vec![
        "/opt/homebrew/bin".into(),
        "/usr/local/bin".into(),
        "/Applications/Docker.app/Contents/Resources/bin".into(),
        format!("{home}/.local/bin"),
        format!("{home}/.cargo/bin"),
        format!("{home}/Library/pnpm"),
        format!("{home}/.volta/bin"),
    ];
    if let Ok(entries) = std::fs::read_dir(format!("{home}/.nvm/versions/node")) {
        let mut versions: Vec<PathBuf> = entries.flatten().map(|e| e.path().join("bin")).collect();
        versions.sort();
        dirs.extend(versions.into_iter().rev().map(|p| p.to_string_lossy().into_owned()));
    }
    dirs.push(std::env::var("PATH").unwrap_or_default());
    dirs.retain(|d| !d.is_empty());
    dirs.join(":")
}

fn command(script: &str, cwd: &Path, envs: &[(String, String)], log: &Path) -> std::io::Result<Command> {
    let out = OpenOptions::new().create(true).append(true).open(log)?;
    let err = out.try_clone()?;
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/zsh".into());
    let mut cmd = Command::new(shell);
    // A login shell reads the user's profile, so their own PATH is honoured too.
    cmd.arg("-lc").arg(script).current_dir(cwd).stdin(Stdio::null()).stdout(out).stderr(err);
    cmd.env("PATH", augmented_path());
    for (key, value) in envs {
        cmd.env(key, value);
    }
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        cmd.process_group(0); // its own group, so stopping it stops everything it started
    }
    Ok(cmd)
}

fn run_blocking(script: &str, cwd: &Path, envs: &[(String, String)], log: &Path) -> std::io::Result<ExitStatus> {
    command(script, cwd, envs, log)?.status()
}

fn spawn(script: &str, cwd: &Path, envs: &[(String, String)], log: &Path) -> std::io::Result<Child> {
    command(script, cwd, envs, log)?.spawn()
}

fn fail(emit: Emit, step: &str, message: &str) -> Result<(), String> {
    emit(step, "error", message);
    Err(message.to_string())
}

impl Services {
    fn track(&self, name: &str, child: Child) {
        self.children.lock().unwrap().push((name.to_string(), child));
    }

    /// True if a service we started has already exited (it crashed on startup).
    fn died(&self, name: &str) -> bool {
        let mut children = self.children.lock().unwrap();
        children
            .iter_mut()
            .find(|(n, _)| n == name)
            .map(|(_, c)| matches!(c.try_wait(), Ok(Some(_))))
            .unwrap_or(false)
    }

    pub fn start_all(&self, config: &Config, log_dir: &Path, emit: Emit) -> Result<(), String> {
        let Some(home) = config.home_path() else {
            return fail(emit, "database", "Choose the DBInsight folder first.");
        };
        if let Err(problem) = validate_home(&home) {
            return fail(emit, "database", &problem);
        }
        std::fs::create_dir_all(log_dir).map_err(|e| e.to_string())?;
        let log = |name: &str| log_dir.join(format!("{name}.log"));
        let api_url = format!("http://localhost:{}", config.api_port);

        // 1. PostgreSQL (and the mail catcher) through Docker Compose.
        emit("database", "starting", "Checking PostgreSQL");
        if !tcp_open(config.database_port) {
            emit("database", "starting", "Starting Docker services (the first start can take a minute)");
            match run_blocking("docker compose up -d postgres mailpit", &home, &[], &log("docker")) {
                Ok(status) if status.success() => {}
                Ok(_) => return fail(emit, "database", "Docker could not start PostgreSQL. Is Docker Desktop running? See the details below."),
                Err(error) => return fail(emit, "database", &format!("Could not run Docker: {error}")),
            }
            if !wait_until(Duration::from_secs(90), || tcp_open(config.database_port)) {
                return fail(emit, "database", &format!("PostgreSQL did not answer on port {}.", config.database_port));
            }
        }
        emit("database", "ready", "PostgreSQL is running");
        // The test apps and the collector, best effort and not waited for.
        if let Ok(mut child) = spawn("docker compose up -d", &home, &[], &log("docker")) {
            std::thread::spawn(move || {
                let _ = child.wait();
            });
        }

        // 2. The analysis API.
        emit("api", "starting", "Starting the analysis API");
        if http_status(config.api_port, "/health") != Some(200) {
            let mut envs = vec![("DBINSIGHT_RESULTS_DATABASE_URL".to_string(), config.database_url.clone())];
            if tcp_open(1025) {
                envs.push(("DBINSIGHT_SMTP_HOST".into(), "localhost".into()));
                envs.push(("DBINSIGHT_SMTP_PORT".into(), "1025".into()));
            }
            let port = config.api_port;
            let script = format!(
                "if [ -x .venv/bin/uvicorn ]; then exec .venv/bin/uvicorn api.dashboard.app:app --port {port}; \
                 else exec uv run uvicorn api.dashboard.app:app --port {port}; fi"
            );
            match spawn(&script, &home.join("services"), &envs, &log("api")) {
                Ok(child) => self.track("api", child),
                Err(error) => return fail(emit, "api", &format!("Could not start the API: {error}")),
            }
            let up = wait_until(Duration::from_secs(60), || self.died("api") || http_status(port, "/health") == Some(200));
            if self.died("api") || !up {
                return fail(emit, "api", "The API did not start. Details below (is the Python environment set up? see the guide).");
            }
        }
        emit("api", "ready", &format!("Listening on port {}", config.api_port));

        // 3. The dashboard.
        emit("dashboard", "starting", "Starting the dashboard");
        let ready = |port: u16| http_status(port, "/login").map(|s| s < 500).unwrap_or(false);
        if !ready(config.dashboard_port) {
            let envs = vec![
                ("DBINSIGHT_API_URL".to_string(), api_url.clone()),
                // The app talks to its own server over http://localhost, where a Secure cookie would not be kept.
                ("DBINSIGHT_COOKIE_SECURE".to_string(), "0".to_string()),
                ("PORT".to_string(), config.dashboard_port.to_string()),
            ];
            let port = config.dashboard_port;
            let script = if config.dev_server {
                format!("exec pnpm --filter dashboard exec next dev --port {port}")
            } else {
                if !home.join("apps/dashboard/.next/BUILD_ID").is_file() {
                    emit("dashboard", "starting", "Building the dashboard (first run only, about a minute)");
                    let built = run_blocking("pnpm --filter dashboard build", &home, &envs, &log("dashboard"));
                    if !matches!(built, Ok(s) if s.success()) {
                        return fail(emit, "dashboard", "The dashboard build failed. Details below.");
                    }
                }
                format!("NODE_ENV=production exec pnpm --filter dashboard exec next start --port {port}")
            };
            match spawn(&script, &home, &envs, &log("dashboard")) {
                Ok(child) => self.track("dashboard", child),
                Err(error) => return fail(emit, "dashboard", &format!("Could not start the dashboard: {error}")),
            }
            let up = wait_until(Duration::from_secs(120), || self.died("dashboard") || ready(port));
            if self.died("dashboard") || !up {
                return fail(emit, "dashboard", "The dashboard did not start. Details below.");
            }
        }
        emit("dashboard", "ready", &format!("Ready on port {}", config.dashboard_port));
        Ok(())
    }

    /// Stop what this app started (and only that): ask nicely, then insist.
    pub fn stop_all(&self) {
        let mut children = self.children.lock().unwrap();
        for (_, child) in children.iter_mut() {
            signal_group(child.id(), "TERM");
        }
        let deadline = Instant::now() + Duration::from_secs(4);
        for (_, child) in children.iter_mut() {
            while Instant::now() < deadline && matches!(child.try_wait(), Ok(None)) {
                std::thread::sleep(Duration::from_millis(100));
            }
            if matches!(child.try_wait(), Ok(None)) {
                signal_group(child.id(), "KILL");
                let _ = child.wait();
            }
        }
        children.clear();
    }

    #[cfg(test)]
    pub fn started_anything(&self) -> bool {
        !self.children.lock().unwrap().is_empty()
    }
}

#[cfg(unix)]
fn signal_group(pid: u32, signal: &str) {
    // A negative pid addresses the whole process group.
    let _ = Command::new("kill").arg(format!("-{signal}")).arg(format!("-{pid}")).status();
}

#[cfg(not(unix))]
fn signal_group(pid: u32, _signal: &str) {
    let _ = Command::new("taskkill").args(["/PID", &pid.to_string(), "/T", "/F"]).status();
}

/// The last `lines` lines of a service's log. Only the known names are readable.
pub fn read_log(log_dir: &Path, name: &str, lines: usize) -> Result<String, String> {
    if !["api", "dashboard", "docker"].contains(&name) {
        return Err(format!("no such log: {name}"));
    }
    let text = std::fs::read_to_string(log_dir.join(format!("{name}.log"))).unwrap_or_default();
    let all: Vec<&str> = text.lines().collect();
    Ok(all[all.len().saturating_sub(lines)..].join("\n"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    fn serve_once(status_line: &'static str) -> u16 {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buffer = [0u8; 256];
                let _ = stream.read(&mut buffer);
                let _ = write!(stream, "{status_line}\r\nContent-Length: 0\r\n\r\n");
            }
        });
        port
    }

    #[test]
    fn a_status_line_is_parsed_and_garbage_is_not() {
        assert_eq!(parse_status("HTTP/1.1 200 OK\r\n"), Some(200));
        assert_eq!(parse_status("HTTP/1.0 307 Temporary Redirect"), Some(307));
        assert_eq!(parse_status("SSH-2.0-OpenSSH"), None);
        assert_eq!(parse_status(""), None);
        assert_eq!(parse_status("HTTP/1.1 abc"), None);
    }

    #[test]
    fn health_checks_see_a_live_server_and_its_status() {
        assert_eq!(http_status(serve_once("HTTP/1.1 200 OK"), "/health"), Some(200));
        assert_eq!(http_status(serve_once("HTTP/1.1 503 Service Unavailable"), "/health"), Some(503));
    }

    #[test]
    fn a_closed_port_is_not_open_and_has_no_status() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        assert!(tcp_open(port));
        drop(listener);
        assert!(!tcp_open(port));
        assert_eq!(http_status(port, "/"), None);
    }

    #[test]
    fn waiting_returns_as_soon_as_the_condition_holds_and_gives_up_otherwise() {
        let mut calls = 0;
        assert!(wait_until(Duration::from_secs(5), || {
            calls += 1;
            calls >= 2
        }));
        assert!(!wait_until(Duration::from_millis(50), || false));
    }

    #[test]
    fn the_search_path_includes_the_usual_tool_locations_and_the_original_path() {
        let path = augmented_path();
        assert!(path.contains("/opt/homebrew/bin") && path.contains("/usr/local/bin"));
        assert!(path.ends_with(&std::env::var("PATH").unwrap_or_default()));
    }

    #[test]
    fn only_known_logs_are_readable_and_only_the_tail_is_returned() {
        let dir = std::env::temp_dir().join(format!("dbinsight-logs-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("api.log"), "one\ntwo\nthree\nfour\n").unwrap();
        assert_eq!(read_log(&dir, "api", 2).unwrap(), "three\nfour");
        assert_eq!(read_log(&dir, "dashboard", 5).unwrap(), "");
        assert!(read_log(&dir, "../../etc/passwd", 5).is_err());
        assert!(read_log(&dir, "config", 5).is_err());
    }

    #[test]
    fn stopping_ends_a_service_and_every_process_it_started() {
        let dir = std::env::temp_dir().join(format!("dbinsight-stop-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let services = Services::default();
        // A shell that starts a grandchild: stopping must reach both.
        let child = spawn("sleep 300 & wait", &dir, &[], &dir.join("t.log")).unwrap();
        let pid = child.id();
        services.track("test", child);
        std::thread::sleep(Duration::from_millis(600));
        assert!(services.started_anything());
        services.stop_all();
        assert!(!services.started_anything());
        let alive = Command::new("kill").arg("-0").arg(pid.to_string()).status().map(|s| s.success()).unwrap_or(false);
        assert!(!alive, "the process group leader should be gone");
    }
}
