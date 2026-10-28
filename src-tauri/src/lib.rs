mod core_process;
use core_process::{CoreProcess, LaunchSpec};
use std::sync::{Arc, Mutex};
use tauri::Manager;

type CoreState = Arc<Mutex<CoreProcess>>;

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
            let mut core =
                CoreProcess::new(LaunchSpec::development().with_data(directory, environment));
            let _ = core.start(); // Failure is shown by the health command; keep the shell usable.
            app.manage(Arc::new(Mutex::new(core)));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![core_health, core_reconnect])
        .build(tauri::generate_context!())
        .expect("AI Asset Hub 실행 실패")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                if let Ok(mut core) = app.state::<CoreState>().lock() {
                    core.stop();
                }
            }
        });
}
