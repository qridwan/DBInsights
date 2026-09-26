fn main() {
    // Declaring the app's own commands puts them under Tauri's permission system: the splash
    // screen (a local page) may call them, the dashboard web app (a remote origin) may not.
    tauri_build::try_build(
        tauri_build::Attributes::new().app_manifest(tauri_build::AppManifest::new().commands(&[
            "get_config",
            "set_home",
            "start_services",
            "stop_services",
            "read_log",
            "open_logs_folder",
        ])),
    )
    .expect("failed to run the Tauri build script");
}
