mod core_process;
mod folder_picker;
use core_process::{CoreProcess, LaunchSpec};
use folder_picker::{FolderPicker, PickedFolder};
use std::sync::{Arc, Mutex};
use tauri::Manager;
use tauri_plugin_dialog::DialogExt;

type CoreState = Arc<Mutex<CoreProcess>>;
#[tauri::command]
async fn search_assets(
    state: tauri::State<'_, CoreState>,
    query: String,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.search",
                serde_json::json!({"query":query,"after_id":after_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn batch_asset_tags(
    state: tauri::State<'_, CoreState>,
    asset_ids: Vec<String>,
    add: Vec<String>,
    remove: Vec<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.tags.batch",
                serde_json::json!({"asset_ids":asset_ids,"add":add,"remove":remove}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn save_asset_annotation(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    title: String,
    description: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.annotate",
                serde_json::json!({"asset_id":asset_id,"title":title,"description":description}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn asset_annotations(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.annotations",
                serde_json::json!({"asset_id":asset_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}
#[tauri::command]
async fn edit_asset_tags(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    add: Vec<String>,
    remove: Vec<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.tags",
                serde_json::json!({"asset_id":asset_id,"add":add,"remove":remove}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn get_asset(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("asset.get", serde_json::json!({"asset_id": asset_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn asset_thumbnail(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("asset.thumbnail", serde_json::json!({"asset_id": asset_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn scan_library(
    state: tauri::State<'_, CoreState>,
    library_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "library.scan",
                serde_json::json!({"library_id": library_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn list_assets(
    state: tauri::State<'_, CoreState>,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("asset.list", serde_json::json!({"after_id": after_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn list_libraries(
    state: tauri::State<'_, CoreState>,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("library.list", serde_json::json!({"after_id": after_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn register_library(
    state: tauri::State<'_, CoreState>,
    picker: tauri::State<'_, FolderPicker>,
    path: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    let picker = picker.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let path = picker.registration_path(&path)?;
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("library.register", serde_json::json!({"path": path}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn unregister_library(
    state: tauri::State<'_, CoreState>,
    library_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "library.unregister",
                serde_json::json!({"library_id": library_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn select_library_folder(
    window: tauri::WebviewWindow,
    picker: tauri::State<'_, FolderPicker>,
) -> Result<Option<PickedFolder>, String> {
    if window.label() != "main" {
        return Err("FOLDER_PICK_FAILED".into());
    }
    let picker = picker.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        picker.choose(|| {
            window
                .dialog()
                .file()
                .set_parent(&window)
                .set_title("라이브러리 폴더 선택")
                .blocking_pick_folder()
                .map(|path| path.into_path().map_err(|_| "FOLDER_LOCAL_ONLY"))
                .transpose()
        })
    })
    .await
    .map_err(|_| "FOLDER_PICK_FAILED".to_owned())?
    .map_err(str::to_owned)
}

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
        .plugin(tauri_plugin_dialog::init())
        .manage(FolderPicker::default())
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
        .invoke_handler(tauri::generate_handler![
            core_health,
            core_reconnect,
            select_library_folder,
            list_libraries,
            register_library,
            unregister_library,
            scan_library,
            list_assets,
            asset_thumbnail,
            get_asset,
            asset_annotations,
            edit_asset_tags,
            save_asset_annotation,
            batch_asset_tags,
            search_assets
        ])
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
