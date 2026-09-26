//! The native menu bar. Standard Edit, View and Window menus (so copy, paste and full screen behave
//! like any Mac app) plus DBInsight's own actions.

use crate::{restart_services, set_home_and_restart};
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Manager};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

pub fn install(app: &AppHandle) -> tauri::Result<()> {
    let app_menu = Submenu::with_items(
        app,
        "DBInsight",
        true,
        &[
            &PredefinedMenuItem::about(app, Some("About DBInsight"), None)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItem::with_id(app, "change_home", "Change DBInsight Folder…", true, None::<&str>)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::hide(app, None)?,
            &PredefinedMenuItem::hide_others(app, None)?,
            &PredefinedMenuItem::show_all(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::quit(app, None)?,
        ],
    )?;
    let edit = Submenu::with_items(
        app,
        "Edit",
        true,
        &[
            &PredefinedMenuItem::undo(app, None)?,
            &PredefinedMenuItem::redo(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, None)?,
            &PredefinedMenuItem::copy(app, None)?,
            &PredefinedMenuItem::paste(app, None)?,
            &PredefinedMenuItem::select_all(app, None)?,
        ],
    )?;
    let view = Submenu::with_items(
        app,
        "View",
        true,
        &[
            &MenuItem::with_id(app, "reload", "Reload", true, Some("CmdOrCtrl+R"))?,
            &MenuItem::with_id(app, "back", "Back", true, Some("CmdOrCtrl+["))?,
            &MenuItem::with_id(app, "forward", "Forward", true, Some("CmdOrCtrl+]"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::fullscreen(app, None)?,
        ],
    )?;
    let window = Submenu::with_items(
        app,
        "Window",
        true,
        &[
            &PredefinedMenuItem::minimize(app, None)?,
            &PredefinedMenuItem::maximize(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::close_window(app, None)?,
        ],
    )?;
    let help = Submenu::with_items(
        app,
        "Help",
        true,
        &[
            &MenuItem::with_id(app, "mailpit", "Open the Email Inbox (development mail)", true, None::<&str>)?,
            &MenuItem::with_id(app, "logs", "Show the Logs Folder", true, None::<&str>)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItem::with_id(app, "restart", "Restart Services", true, None::<&str>)?,
        ],
    )?;
    let menu = Menu::with_items(app, &[&app_menu, &edit, &view, &window, &help])?;
    app.set_menu(menu)?;

    app.on_menu_event(|app, event| {
        let eval = |script: &str| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.eval(script);
            }
        };
        match event.id().as_ref() {
            "reload" => eval("window.location.reload()"),
            "back" => eval("window.history.back()"),
            "forward" => eval("window.history.forward()"),
            "mailpit" => {
                let _ = app.opener().open_url("http://localhost:8025", None::<&str>);
            }
            "logs" => {
                if let Ok(dir) = app.path().app_log_dir() {
                    let _ = std::fs::create_dir_all(&dir);
                    let _ = app.opener().open_path(dir.to_string_lossy(), None::<&str>);
                }
            }
            "restart" => restart_services(app),
            "change_home" => {
                let handle = app.clone();
                app.dialog()
                    .file()
                    .set_title("Choose the DBInsight folder")
                    .pick_folder(move |picked| {
                        if let Some(path) = picked.and_then(|p| p.into_path().ok()) {
                            if let Err(problem) = set_home_and_restart(&handle, path.to_string_lossy().into_owned()) {
                                handle
                                    .dialog()
                                    .message(problem)
                                    .title("That is not a DBInsight folder")
                                    .show(|_| {});
                            }
                        }
                    });
            }
            _ => {}
        }
    });
    Ok(())
}
