-- Historical results and terminal attempts are append-only. Existing data remains intact.
CREATE TRIGGER analysis_results_no_delete BEFORE DELETE ON analysis_results BEGIN
 SELECT RAISE(ABORT,'RESULT_IMMUTABLE');
END;
CREATE TRIGGER analysis_runs_no_delete BEFORE DELETE ON analysis_runs BEGIN
 SELECT RAISE(ABORT,'RUN_IMMUTABLE');
END;
CREATE TRIGGER analysis_runs_final_immutable BEFORE UPDATE ON analysis_runs WHEN old.status!='running' BEGIN
 SELECT RAISE(ABORT,'RUN_IMMUTABLE');
END;
CREATE TRIGGER analysis_runs_identity_immutable BEFORE UPDATE OF id,job_id,asset_id,model_snapshot_json,created_at ON analysis_runs BEGIN
 SELECT RAISE(ABORT,'RUN_IMMUTABLE');
END;
CREATE TRIGGER analysis_jobs_identity_immutable BEFORE UPDATE OF id,request_id,scope_json,model_snapshot_json,requested_count ON analysis_jobs BEGIN
 SELECT RAISE(ABORT,'JOB_SNAPSHOT_IMMUTABLE');
END;
