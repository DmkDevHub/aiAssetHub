mod core_process;
mod folder_picker;
use core_process::{CoreProcess, LaunchSpec};
use folder_picker::{FolderPicker, PickedFolder};
use std::sync::{Arc, Mutex};
use tauri::Manager;
use tauri_plugin_dialog::DialogExt;

type CoreState = Arc<Mutex<CoreProcess>>;
#[tauri::command]
async fn metadata_request(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, CoreState>,
    method: String,
    params: serde_json::Value,
) -> Result<serde_json::Value, String> {
    if window.label() != "main"
        || !matches!(
            method.as_str(),
            "catalog.classification"
                | "catalog.classification.save"
                | "catalog.evidence_candidates"
                | "catalog.options"
                | "catalog.scope"
                | "creator.list"
                | "creator.get"
                | "creator.create"
                | "creator.update"
                | "creator.set_enabled"
                | "creator.links"
                | "creator.links.save"
                | "creator.delete.preview"
                | "creator.delete"
                | "source.list"
                | "source.get"
                | "source.create"
                | "source.update"
                | "source.delete.preview"
                | "source.delete"
                | "license.list"
                | "license.get"
                | "license.create"
                | "license.update"
                | "license.evidence.save"
                | "license.delete.preview"
                | "license.delete"
                | "provenance.history"
                | "provenance.export"
        )
    {
        return Err("CORE_COMMAND_NOT_ALLOWED".into());
    }
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(&method, params)
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn mcp_connection(state: tauri::State<'_, CoreState>) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("mcp.connection", serde_json::json!({}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn mcp_audit(
    state: tauri::State<'_, CoreState>,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("mcp.audit", serde_json::json!({"after_id":after_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn embedding_rebuild(
    state: tauri::State<'_, CoreState>,
    confirmed: bool,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "embedding.rebuild",
                serde_json::json!({"confirmed":confirmed}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[derive(Default, serde::Deserialize, serde::Serialize)]
#[serde(default, deny_unknown_fields)]
struct SemanticCriteria {
    library_id: Option<String>,
    folder_parts: Vec<String>,
    kind: String,
    tag: String,
    analysis: String,
}
#[tauri::command]
async fn embedding_query(
    state: tauri::State<'_, CoreState>,
    query: String,
    mode: String,
    confirmed: bool,
    criteria: Option<SemanticCriteria>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "embedding.query",
                serde_json::json!({"query":query,"mode":mode,"confirmed":confirmed,"criteria":criteria.unwrap_or_default()}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[derive(serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct EmbeddingPair {
    asset_id: String,
    result_id: String,
}
#[tauri::command]
async fn embedding_start(
    state: tauri::State<'_, CoreState>,
    selected: Vec<EmbeddingPair>,
    confirmed: bool,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "embedding.start",
                serde_json::json!({"selected":selected,"confirmed":confirmed}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}
#[tauri::command]
async fn embedding_work(
    state: tauri::State<'_, CoreState>,
    job_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("embedding.work", serde_json::json!({"job_id":job_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn embedding_configure(
    state: tauri::State<'_, CoreState>,
    model_name: String,
    prefix_scheme: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "embedding.configure",
                serde_json::json!({"model_name":model_name,"prefix_scheme":prefix_scheme}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}
#[tauri::command]
async fn embedding_status(state: tauri::State<'_, CoreState>) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("embedding.status", serde_json::json!({}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn asset_analysis_history(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.analysis.history",
                serde_json::json!({"asset_id":asset_id,"after_id":after_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn cancel_analysis(
    state: tauri::State<'_, CoreState>,
    job_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("analysis.cancel", serde_json::json!({"job_id":job_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}
#[tauri::command]
async fn retry_analysis_plan(
    state: tauri::State<'_, CoreState>,
    job_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("analysis.retry_plan", serde_json::json!({"job_id":job_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn analysis_jobs(state: tauri::State<'_, CoreState>) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("analysis.jobs", serde_json::json!({}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn analysis_status(
    state: tauri::State<'_, CoreState>,
    job_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("analysis.status", serde_json::json!({"job_id":job_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}
#[tauri::command]
async fn asset_analysis(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("asset.analysis", serde_json::json!({"asset_id":asset_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[derive(serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct AnalysisStartInput {
    plan: AnalysisPlanInput,
    plan_token: String,
    request_id: String,
    confirmed: bool,
    confirm_external: bool,
    confirm_paid: bool,
}
#[tauri::command]
async fn start_analysis(
    state: tauri::State<'_, CoreState>,
    request: AnalysisStartInput,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "analysis.start",
                serde_json::to_value(request).map_err(|_| "INVALID_PARAMS")?,
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[derive(serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct AnalysisPlanInput {
    mode: String,
    scope: String,
    library_id: Option<String>,
    folder_parts: Vec<String>,
    selected_ids: Vec<String>,
    model_id: String,
}
#[tauri::command]
async fn preview_analysis(
    state: tauri::State<'_, CoreState>,
    plan: AnalysisPlanInput,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "analysis.preview",
                serde_json::to_value(plan).map_err(|_| "INVALID_PARAMS")?,
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn validate_model(
    state: tauri::State<'_, CoreState>,
    id: String,
    modality: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "model.validate",
                serde_json::json!({"id":id,"modality":modality}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}
#[tauri::command]
async fn select_model(
    state: tauri::State<'_, CoreState>,
    id: String,
    modality: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "model.select",
                serde_json::json!({"id":id,"modality":modality}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[derive(serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct ModelPolicyInput {
    id: String,
    enabled: bool,
    allow_external: bool,
    allow_paid: bool,
    budget_usd: String,
    max_requests: u32,
}
#[tauri::command]
async fn configure_model(
    state: tauri::State<'_, CoreState>,
    policy: ModelPolicyInput,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "model.policy",
                serde_json::to_value(policy).map_err(|_| "INVALID_PARAMS")?,
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn model_credential(
    state: tauri::State<'_, CoreState>,
    id: String,
    action: String,
    key: Option<String>,
    allow_external: Option<bool>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move||state.lock().map_err(|_|"CORE_UNAVAILABLE")?.library_request("model.credential",serde_json::json!({"id":id,"action":action,"key":key,"allow_external":allow_external.unwrap_or(false)}))).await.map_err(|_|"CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn inspect_model(
    state: tauri::State<'_, CoreState>,
    id: String,
    allow_external: Option<bool>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "model.inspect",
                serde_json::json!({"id":id,"allow_external":allow_external.unwrap_or(false)}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn list_models(
    state: tauri::State<'_, CoreState>,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("model.list", serde_json::json!({"after_id":after_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}
#[tauri::command]
async fn register_model(
    state: tauri::State<'_, CoreState>,
    provider_name: String,
    kind: String,
    model_id: String,
    modalities: Vec<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("model.register",serde_json::json!({"provider_name":provider_name,"kind":kind,"model_id":model_id,"modalities":modalities}))).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

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
    aliases: Option<Vec<String>>,
    expected_revision: Option<u64>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut params =
            serde_json::json!({"asset_id":asset_id,"title":title,"description":description});
        if let Some(aliases) = aliases {
            params["aliases"] = serde_json::json!(aliases);
            params["expected_revision"] = serde_json::json!(expected_revision);
        } else if expected_revision.is_some() {
            return Err("INVALID_PARAMS");
        }
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("asset.annotate", params)
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn get_asset_management(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("asset.management", serde_json::json!({"asset_id":asset_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn save_asset_management(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    value: serde_json::Value,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.management.save", serde_json::json!({"asset_id":asset_id,"value":value,"expected_revision":expected_revision}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn get_asset_composition(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.composition",
                serde_json::json!({"asset_id":asset_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn save_asset_composition(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    value: serde_json::Value,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.composition.save", serde_json::json!({"asset_id":asset_id,"value":value,"expected_revision":expected_revision}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn asset_link_candidates(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    kind: String,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.link.candidates",
                serde_json::json!({"asset_id":asset_id,"kind":kind,"after_id":after_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn get_asset_relations(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("asset.relations", serde_json::json!({"asset_id":asset_id}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn save_asset_relations(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    value: serde_json::Value,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.relations.save", serde_json::json!({"asset_id":asset_id,"value":value,"expected_revision":expected_revision}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn asset_metadata_history(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    before_id: Option<u64>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.metadata.history",
                serde_json::json!({"asset_id":asset_id,"before_id":before_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn group_list(
    state: tauri::State<'_, CoreState>,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.groups.list",
                serde_json::json!({"after_id":after_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn group_create(
    state: tauri::State<'_, CoreState>,
    value: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("asset.groups.create", serde_json::json!({"value":value}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn group_update(
    state: tauri::State<'_, CoreState>,
    group_id: String,
    value: serde_json::Value,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.groups.update", serde_json::json!({"group_id":group_id,"value":value,"expected_revision":expected_revision}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn group_delete(
    state: tauri::State<'_, CoreState>,
    group_id: String,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.groups.delete",
                serde_json::json!({"group_id":group_id,"expected_revision":expected_revision}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn group_membership(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.groups.membership",
                serde_json::json!({"asset_id":asset_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn group_assign(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    group_ids: Vec<String>,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.groups.assign", serde_json::json!({"asset_id":asset_id,"group_ids":group_ids,"expected_revision":expected_revision}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn group_move(
    state: tauri::State<'_, CoreState>,
    group_id: String,
    parent_id: Option<String>,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.groups.move", serde_json::json!({"group_id":group_id,"parent_id":parent_id,"expected_revision":expected_revision}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn group_query(
    state: tauri::State<'_, CoreState>,
    group_id: String,
    query: String,
    criteria: serde_json::Value,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.groups.query", serde_json::json!({"group_id":group_id,"query":query,"criteria":criteria,"after_id":after_id}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn group_batch_preview(
    state: tauri::State<'_, CoreState>,
    asset_ids: Vec<String>,
    add: Vec<String>,
    remove: Vec<String>,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.groups.batch_preview", serde_json::json!({"asset_ids":asset_ids,"add":add,"remove":remove,"after_id":after_id}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn group_batch_apply(
    state: tauri::State<'_, CoreState>,
    plan: serde_json::Value,
    confirmed: bool,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.groups.batch_apply",
                serde_json::json!({"plan":plan,"confirmed":confirmed}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn package_list(
    state: tauri::State<'_, CoreState>,
    after_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.packages.list",
                serde_json::json!({"after_id":after_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn package_create(
    state: tauri::State<'_, CoreState>,
    value: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("asset.packages.create", serde_json::json!({"value":value}))
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn package_update(
    state: tauri::State<'_, CoreState>,
    package_id: String,
    value: serde_json::Value,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.packages.update", serde_json::json!({"package_id":package_id,"value":value,"expected_revision":expected_revision}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn package_delete(
    state: tauri::State<'_, CoreState>,
    package_id: String,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.packages.delete",
                serde_json::json!({"package_id":package_id,"expected_revision":expected_revision}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn package_membership(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.packages.membership",
                serde_json::json!({"asset_id":asset_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn package_assign(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    package_ids: Vec<String>,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.packages.assign", serde_json::json!({"asset_id":asset_id,"package_ids":package_ids,"expected_revision":expected_revision}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn package_defaults(
    state: tauri::State<'_, CoreState>,
    package_id: String,
    value: serde_json::Value,
    expected_revision: u64,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.packages.defaults", serde_json::json!({"package_id":package_id,"value":value,"expected_revision":expected_revision}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
}

#[tauri::command]
async fn package_effective(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request(
                "asset.packages.effective",
                serde_json::json!({"asset_id":asset_id}),
            )
    })
    .await
    .map_err(|_| "CORE_UNAVAILABLE".to_string())?
    .map_err(str::to_owned)
}

#[tauri::command]
async fn package_override(
    state: tauri::State<'_, CoreState>,
    asset_id: String,
    value: serde_json::Value,
    expected_revision: u64,
    expected_packages: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        state.lock().map_err(|_| "CORE_UNAVAILABLE")?.library_request("asset.packages.override", serde_json::json!({"asset_id":asset_id,"value":value,"expected_revision":expected_revision,"expected_packages":expected_packages}))
    }).await.map_err(|_| "CORE_UNAVAILABLE".to_string())?.map_err(str::to_owned)
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
    expected_revision: Option<u64>,
) -> Result<serde_json::Value, String> {
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut params = serde_json::json!({"asset_id":asset_id,"add":add,"remove":remove});
        if let Some(revision) = expected_revision {
            params["expected_revision"] = serde_json::json!(revision);
        }
        state
            .lock()
            .map_err(|_| "CORE_UNAVAILABLE")?
            .library_request("asset.tags", params)
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
            metadata_request,
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
            get_asset_management,
            save_asset_management,
            get_asset_composition,
            save_asset_composition,
            asset_link_candidates,
            get_asset_relations,
            save_asset_relations,
            asset_metadata_history,
            group_list,
            group_create,
            group_update,
            group_delete,
            group_membership,
            group_assign,
            group_move,
            group_query,
            group_batch_preview,
            group_batch_apply,
            package_list,
            package_create,
            package_update,
            package_delete,
            package_membership,
            package_assign,
            package_defaults,
            package_effective,
            package_override,
            asset_annotations,
            edit_asset_tags,
            save_asset_annotation,
            batch_asset_tags,
            search_assets,
            list_models,
            register_model,
            inspect_model,
            model_credential,
            configure_model,
            validate_model,
            select_model,
            preview_analysis,
            start_analysis,
            analysis_status,
            asset_analysis,
            analysis_jobs,
            cancel_analysis,
            retry_analysis_plan,
            asset_analysis_history,
            embedding_configure,
            embedding_status,
            embedding_start,
            embedding_work,
            embedding_query,
            embedding_rebuild,
            mcp_connection,
            mcp_audit
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
