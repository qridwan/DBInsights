//! DBInsight desktop: a native shell around the dashboard.
//!
//! It shows a splash screen while it makes sure PostgreSQL, the analysis API and the dashboard are
//! running (starting what is not), then loads the dashboard in the same native window. It stops
//! what it started when it quits. The dashboard itself is the Next.js app; this is not a rewrite of it.

mod config;
mod menu;
mod services;

use config::{validate_home, Config};
use serde::Serialize;
use services::Services;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, Url, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;

pub struct AppState {
    services: Arc<Services>,
    config: Mutex<Config>,
    config_dir: PathBuf,
    log_dir: PathBuf,
    starting: AtomicBool,
}

#[derive(Serialize)]
struct ConfigView {
    home: Option<String>,
    home_ok: bool,
    api_port: u16,
    dashboard_port: u16,
    log_dir: String,
}

#[derive(Serialize, Clone)]
struct Status {
    step: String,
    state: String,
    detail: String,
}

fn view(state: &AppState) -> ConfigView {
    let config = state.config.lock().unwrap();
    ConfigView {
        home: config.home.clone(),
        home_ok: config.home_path().map(|h| validate_home(&h).is_ok()).unwrap_or(false),
        api_port: config.api_port,
        dashboard_port: config.dashboard_port,
        log_dir: state.log_dir.to_string_lossy().into_owned(),
    }
}

/// Append a line to `desktop.log`, so a problem can be diagnosed after the fact.
fn note(log_dir: &Path, message: &str) {
    use std::io::Write;
    if std::fs::create_dir_all(log_dir).is_err() {
        return;
    }
    let seconds = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(log_dir.join("desktop.log")) {
        let _ = writeln!(file, "[{seconds}] {message}");
    }
}

const SPLASH: &str = if cfg!(windows) { "http://tauri.localhost/index.html" } else { "tauri://localhost/index.html" };

fn go(app: &AppHandle, url: &str) {
    if let Some(window) = app.get_webview_window("main") {
        let target = serde_json::to_string(url).unwrap_or_else(|_| "\"\"".into());
        let _ = window.eval(&format!("window.location.replace({target})"));
    }
}

/// Start (or check) the services on a background thread, reporting each step to the splash screen,
/// and open the dashboard when they are all up.
pub fn begin_start(app: &AppHandle) {
    let state = app.state::<AppState>();
    if state.starting.swap(true, Ordering::SeqCst) {
        return; // already in progress
    }
    let config = state.config.lock().unwrap().clone();
    let services = state.services.clone();
    let log_dir = state.log_dir.clone();
    let app = app.clone();
    note(&log_dir, &format!("starting services (home: {:?}, dev server: {})", config.home, config.dev_server));
    std::thread::spawn(move || {
        let emitter = app.clone();
        let notes = log_dir.clone();
        let emit = move |step: &str, state: &str, detail: &str| {
            note(&notes, &format!("{step}: {state}: {detail}"));
            let _ = emitter.emit("service-status", Status { step: step.into(), state: state.into(), detail: detail.into() });
        };
        if services.start_all(&config, &log_dir, &emit).is_ok() {
            let _ = app.emit("services-ready", ());
            std::thread::sleep(Duration::from_millis(500));
            go(&app, &format!("http://localhost:{}/", config.dashboard_port));
        }
        app.state::<AppState>().starting.store(false, Ordering::SeqCst);
    });
}

/// Stop what this app started, show the splash again, and start everything afresh.
pub fn restart_services(app: &AppHandle) {
    app.state::<AppState>().services.stop_all();
    go(app, SPLASH);
}

pub fn set_home_and_restart(app: &AppHandle, path: String) -> Result<(), String> {
    validate_home(Path::new(&path))?;
    let state = app.state::<AppState>();
    {
        let mut config = state.config.lock().unwrap();
        config.home = Some(path);
        config.save(&state.config_dir)?;
    }
    restart_services(app);
    Ok(())
}

// ---- commands (callable by the splash screen only; see capabilities/) ------------------------

#[tauri::command]
fn get_config(state: State<'_, AppState>) -> ConfigView {
    view(&state)
}

#[tauri::command]
fn set_home(state: State<'_, AppState>, path: String) -> Result<ConfigView, String> {
    validate_home(Path::new(&path))?;
    {
        let mut config = state.config.lock().unwrap();
        config.home = Some(path);
        config.save(&state.config_dir)?;
    }
    Ok(view(&state))
}

#[tauri::command]
fn start_services(app: AppHandle) {
    begin_start(&app);
}

#[tauri::command]
fn stop_services(state: State<'_, AppState>) {
    state.services.stop_all();
}

#[tauri::command]
fn read_log(state: State<'_, AppState>, name: String, lines: usize) -> Result<String, String> {
    services::read_log(&state.log_dir, &name, lines.min(500))
}

#[tauri::command]
fn open_logs_folder(app: AppHandle) -> Result<(), String> {
    let dir = app.state::<AppState>().log_dir.clone();
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    app.opener().open_path(dir.to_string_lossy(), None::<&str>).map_err(|e| e.to_string())
}

/// Which addresses the window may show. Everything else opens in the person's own browser, so a link
/// in the dashboard can never replace the app with some other website.
fn allowed(url: &Url, dashboard_port: u16, dev_url: Option<&Url>) -> bool {
    // `tauri dev` serves the splash page from its own local dev server, not from tauri://.
    if let Some(dev) = dev_url {
        if url.scheme() == dev.scheme() && url.host_str() == dev.host_str() && url.port() == dev.port() {
            return true;
        }
    }
    match url.scheme() {
        "tauri" | "asset" | "about" | "blob" | "data" => true,
        "http" | "https" => match url.host_str() {
            Some("tauri.localhost") => true,
            Some("localhost") | Some("127.0.0.1") => url.port() == Some(dashboard_port),
            _ => false,
        },
        _ => false,
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // A second launch would fight over the same ports: bring the first window forward.
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .setup(|app| {
            let config_dir = app.path().app_config_dir()?;
            let log_dir = app.path().app_log_dir()?;
            let config = Config::load(&config_dir);
            let dashboard_port = config.dashboard_port;
            let services = Arc::new(Services::default());
            {
                // Quitting from the menu runs the cleanup below. A plain SIGTERM/SIGINT/SIGHUP (a `kill`,
                // logging out) would skip it and leave the services this app started running, so it
                // is handled the same way.
                let services = services.clone();
                let _ = ctrlc::set_handler(move || {
                    services.stop_all();
                    std::process::exit(0);
                });
            }
            app.manage(AppState {
                services,
                config: Mutex::new(config),
                config_dir,
                log_dir,
                starting: AtomicBool::new(false),
            });

            let page_log = app.state::<AppState>().log_dir.clone();
            note(&page_log, &format!("app started (home: {:?})", app.state::<AppState>().config.lock().unwrap().home));
            let dev_url = app.config().build.dev_url.clone();
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("DBInsight")
                .inner_size(1360.0, 860.0)
                .min_inner_size(960.0, 620.0)
                .center()
                .on_page_load(move |_window, payload| {
                    if matches!(payload.event(), tauri::webview::PageLoadEvent::Finished) {
                        note(&page_log, &format!("page loaded: {}", payload.url()));
                    }
                })
                .on_navigation(move |url| {
                    let ok = allowed(url, dashboard_port, dev_url.as_ref());
                    if !ok && matches!(url.scheme(), "http" | "https") {
                        let _ = tauri_plugin_opener::open_url(url.as_str(), None::<&str>);
                    }
                    ok
                })
                .build()?;

            menu::install(app.handle())?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_config,
            set_home,
            start_services,
            stop_services,
            read_log,
            open_logs_folder
        ])
        .build(tauri::generate_context!())
        .expect("error while building the DBInsight desktop app")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                app.state::<AppState>().services.stop_all();
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    const DEFAULT_CAPABILITY: &str = include_str!("../capabilities/default.json");
    const DASHBOARD_CAPABILITY: &str = include_str!("../capabilities/dashboard.json");
    const BUILD_SCRIPT: &str = include_str!("../build.rs");

    fn permissions(json: &str) -> Vec<String> {
        let value: serde_json::Value = serde_json::from_str(json).unwrap();
        value["permissions"].as_array().unwrap().iter().map(|p| p.as_str().unwrap().to_string()).collect()
    }

    #[test]
    fn the_dashboard_web_app_may_use_the_folder_dialog_and_nothing_else() {
        assert_eq!(permissions(DASHBOARD_CAPABILITY), vec!["dialog:allow-open"]);
        let value: serde_json::Value = serde_json::from_str(DASHBOARD_CAPABILITY).unwrap();
        let urls: Vec<&str> = value["remote"]["urls"].as_array().unwrap().iter().map(|u| u.as_str().unwrap()).collect();
        assert_eq!(urls, vec!["http://localhost:3003/*", "http://127.0.0.1:3003/*"]);
    }

    #[test]
    fn the_splash_screen_capability_is_local_only_and_the_dashboard_one_grants_no_app_command() {
        let splash: serde_json::Value = serde_json::from_str(DEFAULT_CAPABILITY).unwrap();
        assert!(splash.get("remote").is_none(), "the splash capability must not apply to a remote address");
        assert!(permissions(DASHBOARD_CAPABILITY).iter().all(|p| !p.starts_with("allow-")));
    }

    #[test]
    fn every_app_command_is_declared_and_granted_to_the_splash_screen() {
        let granted = permissions(DEFAULT_CAPABILITY);
        for command in ["get_config", "set_home", "start_services", "stop_services", "read_log", "open_logs_folder"] {
            assert!(BUILD_SCRIPT.contains(&format!("\"{command}\"")), "{command} is not declared in build.rs");
            assert!(granted.contains(&format!("allow-{}", command.replace('_', "-"))), "{command} is not granted");
        }
    }

    fn url(text: &str) -> Url {
        Url::parse(text).unwrap()
    }

    #[test]
    fn the_window_may_show_its_own_pages_and_the_dashboard_only() {
        assert!(allowed(&url("tauri://localhost/index.html"), 3003, None));
        assert!(allowed(&url("http://tauri.localhost/index.html"), 3003, None));
        assert!(allowed(&url("http://localhost:3003/login"), 3003, None));
        assert!(allowed(&url("http://127.0.0.1:3003/"), 3003, None));
    }

    #[test]
    fn the_dev_server_is_shown_only_when_one_is_configured() {
        let dev = url("http://127.0.0.1:1430/");
        assert!(allowed(&url("http://127.0.0.1:1430/index.html"), 3003, Some(&dev)));
        assert!(!allowed(&url("http://127.0.0.1:1430/"), 3003, None));
        assert!(!allowed(&url("http://127.0.0.1:1431/"), 3003, Some(&dev)));
    }

    #[test]
    fn other_sites_and_other_local_ports_are_not_shown_in_the_app_window() {
        assert!(!allowed(&url("https://example.com/"), 3003, None));
        assert!(!allowed(&url("http://localhost:8710/v1/apps"), 3003, None));
        assert!(!allowed(&url("http://localhost/"), 3003, None));
        assert!(!allowed(&url("http://evil.localhost:3003/"), 3003, None));
        assert!(!allowed(&url("ftp://localhost:3003/"), 3003, None));
        assert!(!allowed(&url("file:///etc/passwd"), 3003, None));
    }
}
