mod core_process;
use core_process::{CoreProcess, LaunchSpec};
use std::sync::{Arc, Mutex};
use tauri::Manager;

type CoreState = Arc<Mutex<CoreProcess>>;

/// Deployment automation only; never builds a window or touches the user's AppData.
pub fn verify_packaged_core(data: std::path::PathBuf) -> Result<serde_json::Value, String> {
    if !data.is_absolute()
        || data.exists()
        || !data
            .file_name()
            .is_some_and(|name| name.to_string_lossy().starts_with("core-verification-"))
    {
        return Err("VERIFICATION_PATH_INVALID".into());
    }
    let executable = std::env::current_exe().map_err(|_| "CORE_START_FAILED")?;
    let directory = executable
        .parent()
        .ok_or("CORE_START_FAILED")?
        .to_path_buf();
    let mut core = CoreProcess::new(LaunchSpec::packaged(directory).with_data(data, "production"));
    let response = core.start().map_err(str::to_string)?;
    core.stop();
    Ok(response)
}

#[tauri::command]
async fn core_health(state: tauri::State<'_, CoreState>) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.health()
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_string)
}

#[tauri::command]
async fn core_reconnect(state: tauri::State<'_, CoreState>) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.start()
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_string)
}

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let (directory, environment) = core_process::data_location(
                cfg!(debug_assertions),
                app.path().app_local_data_dir()?,
            );
            let launch = if cfg!(debug_assertions) {
                LaunchSpec::development()
            } else {
                LaunchSpec::packaged(
                    std::env::current_exe()?
                        .parent()
                        .ok_or("Missing application directory")?
                        .to_path_buf(),
                )
            };
            let mut core = CoreProcess::new(launch.with_data(directory, environment));
            let _ = core.start(); // Failure is shown by the health command; keep the shell usable.
            app.manage(Arc::new(Mutex::new(core)));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![core_health, core_reconnect])
        .build(tauri::generate_context!())
        .expect("AI Asset Hub 실행 실패")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit)
                && let Ok(mut core) = app.state::<CoreState>().lock()
            {
                core.stop();
            }
        });
}
