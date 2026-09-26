//! Where the DBInsight checkout lives and which ports the services use. Stored as JSON in the app's
//! config directory so the choice survives restarts.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub const DEFAULT_DATABASE_URL: &str = "postgresql://dbinsight:dbinsight@localhost:5432/dbinsight";

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
#[serde(default)]
pub struct Config {
    /// The DBInsight checkout (the folder that holds `apps`, `services` and `packages`).
    pub home: Option<String>,
    pub api_port: u16,
    pub dashboard_port: u16,
    pub database_port: u16,
    pub database_url: String,
    /// Run the dashboard with `next dev` (hot reload) instead of a production build.
    pub dev_server: bool,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            home: None,
            api_port: 8710,
            dashboard_port: 3003,
            database_port: 5432,
            database_url: DEFAULT_DATABASE_URL.to_string(),
            // `tauri dev` is for developing the dashboard; a release app runs the built one.
            dev_server: cfg!(debug_assertions),
        }
    }
}

impl Config {
    pub fn home_path(&self) -> Option<PathBuf> {
        self.home.as_ref().map(PathBuf::from)
    }

    /// The saved configuration, or defaults. A missing home is filled in by looking around.
    pub fn load(dir: &Path) -> Config {
        let mut config: Config = std::fs::read_to_string(dir.join("config.json"))
            .ok()
            .and_then(|text| serde_json::from_str(&text).ok())
            .unwrap_or_default();
        let saved_home_ok = config.home_path().map(|h| validate_home(&h).is_ok()).unwrap_or(false);
        if !saved_home_ok {
            config.home = discover_home().map(|p| p.to_string_lossy().into_owned());
        }
        config
    }

    pub fn save(&self, dir: &Path) -> Result<(), String> {
        std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
        let text = serde_json::to_string_pretty(self).map_err(|e| e.to_string())?;
        std::fs::write(dir.join("config.json"), text).map_err(|e| e.to_string())
    }
}

/// A folder is a DBInsight checkout if it has the API and the dashboard in the expected places.
pub fn validate_home(path: &Path) -> Result<(), String> {
    let needed = ["services/api/dashboard/app.py", "apps/dashboard/package.json"];
    for file in needed {
        if !path.join(file).is_file() {
            return Err(format!(
                "{} does not look like a DBInsight folder (missing {file}).",
                path.display()
            ));
        }
    }
    Ok(())
}

/// Find a checkout without asking: `DBINSIGHT_HOME`, then the folders above the running program
/// and above the working directory (which is how it is found during development).
pub fn discover_home() -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(home) = std::env::var("DBINSIGHT_HOME") {
        candidates.push(PathBuf::from(home));
    }
    for start in [std::env::current_exe().ok(), std::env::current_dir().ok()].into_iter().flatten() {
        candidates.extend(start.ancestors().map(Path::to_path_buf));
    }
    candidates.into_iter().find(|c| validate_home(c).is_ok())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn checkout(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("dbinsight-test-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(dir.join("services/api/dashboard")).unwrap();
        std::fs::create_dir_all(dir.join("apps/dashboard")).unwrap();
        std::fs::write(dir.join("services/api/dashboard/app.py"), "").unwrap();
        std::fs::write(dir.join("apps/dashboard/package.json"), "{}").unwrap();
        dir
    }

    #[test]
    fn a_real_checkout_validates_and_an_empty_folder_says_what_is_missing() {
        let good = checkout("valid");
        assert!(validate_home(&good).is_ok());
        let empty = std::env::temp_dir().join(format!("dbinsight-empty-{}", std::process::id()));
        std::fs::create_dir_all(&empty).unwrap();
        let error = validate_home(&empty).unwrap_err();
        assert!(error.contains("services/api/dashboard/app.py"), "{error}");
    }

    #[test]
    fn configuration_round_trips_and_unknown_or_missing_fields_fall_back_to_defaults() {
        let dir = std::env::temp_dir().join(format!("dbinsight-cfg-{}", std::process::id()));
        let mut config = Config::default();
        config.home = Some("/somewhere".into());
        config.api_port = 9999;
        config.save(&dir).unwrap();
        let text = std::fs::read_to_string(dir.join("config.json")).unwrap();
        let back: Config = serde_json::from_str(&text).unwrap();
        assert_eq!(back, config);
        let partial: Config = serde_json::from_str(r#"{"api_port": 1234}"#).unwrap();
        assert_eq!((partial.api_port, partial.dashboard_port), (1234, 3003));
    }

    #[test]
    fn a_stale_saved_home_is_replaced_by_discovery_and_a_valid_one_is_kept() {
        let good = checkout("keep");
        let dir = std::env::temp_dir().join(format!("dbinsight-load-{}", std::process::id()));
        let mut config = Config::default();
        config.home = Some(good.to_string_lossy().into_owned());
        config.save(&dir).unwrap();
        assert_eq!(Config::load(&dir).home, config.home);

        config.home = Some("/definitely/not/here".into());
        config.save(&dir).unwrap();
        let loaded = Config::load(&dir);
        assert_ne!(loaded.home.as_deref(), Some("/definitely/not/here"));
    }

    #[test]
    fn the_environment_variable_names_a_checkout() {
        let good = checkout("env");
        std::env::set_var("DBINSIGHT_HOME", &good);
        assert_eq!(discover_home(), Some(good));
        std::env::remove_var("DBINSIGHT_HOME");
    }
}
