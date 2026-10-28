"""Read persisted success possession separately from the most recent attempt."""


def asset_state(db, identifier):
    active=db.execute('''SELECT r.created_at,run.input_fingerprint,f.sha256,f.exists_flag FROM asset_active_results ar
        JOIN analysis_results r ON r.id=ar.analysis_result_id JOIN analysis_runs run ON run.id=r.run_id
        LEFT JOIN asset_files f ON f.asset_id=ar.asset_id WHERE ar.asset_id=?''',(identifier,)).fetchone()
    latest=db.execute('''SELECT i.status,i.error_code,j.id FROM analysis_job_items i JOIN analysis_jobs j ON j.id=i.job_id
        WHERE i.asset_id=? ORDER BY j.created_at DESC,j.rowid DESC LIMIT 1''',(identifier,)).fetchone()
    run=db.execute('''SELECT status FROM analysis_runs WHERE asset_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1''',(identifier,)).fetchone()
    state=run[0] if run else None
    if latest:
        attempt=db.execute('SELECT status FROM analysis_runs WHERE asset_id=? AND job_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(identifier,latest[2])).fetchone()
        state=latest[0] if latest[0] in ('queued','running') or not attempt else attempt[0]
    return {'hasActiveResult':bool(active),'lastAttemptState':state,
            'lastAnalysisAt':active[0] if active else None,
            'analysisStale':bool(active and (not active[3] or active[2] is None or active[1]!=active[2])),
            'lastAnalysisError':latest[1] if latest else None}
