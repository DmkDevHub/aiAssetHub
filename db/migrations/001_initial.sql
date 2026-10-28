CREATE TABLE library_roots (
 id TEXT PRIMARY KEY, display_name TEXT NOT NULL, absolute_path TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
CREATE TABLE assets (
 id TEXT PRIMARY KEY, library_root_id TEXT NOT NULL REFERENCES library_roots(id), display_name TEXT NOT NULL, category TEXT,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE asset_files (
 id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), relative_path TEXT NOT NULL, absolute_path TEXT NOT NULL UNIQUE,
 extension TEXT NOT NULL, size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0), mtime_ns INTEGER NOT NULL, sha256 TEXT,
 exists_flag INTEGER NOT NULL DEFAULT 1 CHECK(exists_flag IN (0,1))
);
CREATE INDEX asset_files_asset ON asset_files(asset_id);
CREATE TABLE asset_observations (
 asset_file_id TEXT PRIMARY KEY REFERENCES asset_files(id), width INTEGER, height INTEGER, duration_ms INTEGER,
 metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json)), scanned_at TEXT NOT NULL
);
CREATE TABLE tags (id TEXT PRIMARY KEY, label TEXT NOT NULL, normalized_label TEXT NOT NULL UNIQUE);
CREATE TABLE asset_user_annotations (asset_id TEXT PRIMARY KEY REFERENCES assets(id), title_override TEXT, description_override TEXT, updated_at TEXT NOT NULL);
CREATE TABLE model_providers (id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('local','external')));
CREATE TABLE model_registry (
 id TEXT PRIMARY KEY, provider_id TEXT NOT NULL REFERENCES model_providers(id), model_id TEXT NOT NULL,
 modalities_json TEXT NOT NULL CHECK(json_valid(modalities_json)), capabilities_json TEXT NOT NULL CHECK(json_valid(capabilities_json)),
 cost_json TEXT CHECK(cost_json IS NULL OR json_valid(cost_json)), enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1))
);
CREATE TABLE analysis_jobs (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, scope_json TEXT NOT NULL CHECK(json_valid(scope_json)), model_snapshot_json TEXT NOT NULL CHECK(json_valid(model_snapshot_json)),
 requested_count INTEGER NOT NULL CHECK(requested_count >= 0), status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','canceled')),
 created_at TEXT NOT NULL, started_at TEXT, ended_at TEXT, initiated_by TEXT NOT NULL, cost_limit REAL CHECK(cost_limit IS NULL OR cost_limit >= 0)
);
CREATE TABLE analysis_job_items (
 job_id TEXT NOT NULL REFERENCES analysis_jobs(id), asset_id TEXT NOT NULL REFERENCES assets(id),
 status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','canceled')), attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
 error_code TEXT, started_at TEXT, ended_at TEXT, PRIMARY KEY(job_id,asset_id)
);
CREATE TABLE analysis_runs (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL, asset_id TEXT NOT NULL, model_snapshot_json TEXT NOT NULL CHECK(json_valid(model_snapshot_json)),
 input_fingerprint TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('running','completed','failed','canceled')),
 usage_json TEXT CHECK(usage_json IS NULL OR json_valid(usage_json)), error_json TEXT CHECK(error_json IS NULL OR json_valid(error_json)), created_at TEXT NOT NULL,
 UNIQUE(asset_id,id), FOREIGN KEY(job_id,asset_id) REFERENCES analysis_job_items(job_id,asset_id)
);
CREATE TABLE analysis_results (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE, asset_id TEXT NOT NULL, description TEXT NOT NULL, category TEXT,
 tags_json TEXT NOT NULL CHECK(json_valid(tags_json)), features_json TEXT NOT NULL CHECK(json_valid(features_json)),
 confidence REAL CHECK(confidence IS NULL OR confidence BETWEEN 0 AND 1), created_at TEXT NOT NULL,
 UNIQUE(asset_id,id), FOREIGN KEY(asset_id,run_id) REFERENCES analysis_runs(asset_id,id)
);
CREATE TRIGGER analysis_results_require_success BEFORE INSERT ON analysis_results
BEGIN
 SELECT CASE WHEN (SELECT status FROM analysis_runs WHERE id=NEW.run_id) != 'completed' THEN RAISE(ABORT,'RESULT_REQUIRES_SUCCESS') END;
END;
CREATE TRIGGER analysis_results_immutable BEFORE UPDATE ON analysis_results
BEGIN
 SELECT RAISE(ABORT,'RESULT_IMMUTABLE');
END;
CREATE TABLE asset_active_results (
 asset_id TEXT PRIMARY KEY REFERENCES assets(id), analysis_result_id TEXT NOT NULL, selected_at TEXT NOT NULL,
 FOREIGN KEY(asset_id,analysis_result_id) REFERENCES analysis_results(asset_id,id)
);
CREATE TABLE asset_tags (
 asset_id TEXT NOT NULL REFERENCES assets(id), tag_id TEXT NOT NULL REFERENCES tags(id), source TEXT NOT NULL CHECK(source IN ('user','ai')),
 analysis_result_id TEXT, PRIMARY KEY(asset_id,tag_id,source),
 CHECK((source='user' AND analysis_result_id IS NULL) OR (source='ai' AND analysis_result_id IS NOT NULL)),
 FOREIGN KEY(asset_id,analysis_result_id) REFERENCES analysis_results(asset_id,id)
);
CREATE TABLE search_documents (asset_id TEXT PRIMARY KEY REFERENCES assets(id), searchable_text TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE asset_embeddings (
 asset_id TEXT NOT NULL REFERENCES assets(id), result_id TEXT, embedding_model TEXT NOT NULL, dimension INTEGER NOT NULL CHECK(dimension > 0),
 vector_blob BLOB NOT NULL, input_fingerprint TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(asset_id,embedding_model),
 FOREIGN KEY(asset_id,result_id) REFERENCES analysis_results(asset_id,id)
);
CREATE TABLE unity_operations (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, asset_id TEXT NOT NULL REFERENCES assets(id), project_path TEXT NOT NULL,
 action TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)), created_at TEXT NOT NULL
);
CREATE TABLE audit_events (
 id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT, outcome TEXT NOT NULL,
 created_at TEXT NOT NULL, details_redacted_json TEXT NOT NULL CHECK(json_valid(details_redacted_json))
);
CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL CHECK(json_valid(value_json)), updated_at TEXT NOT NULL);
