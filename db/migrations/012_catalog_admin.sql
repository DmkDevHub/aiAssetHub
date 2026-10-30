ALTER TABLE tags ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1));
ALTER TABLE tags ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0);
CREATE TABLE catalog_admin_history (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, entity_id TEXT NOT NULL, version TEXT NOT NULL,
 before_json TEXT NOT NULL CHECK(json_valid(before_json)), after_json TEXT NOT NULL CHECK(json_valid(after_json)), created_at TEXT NOT NULL
);
CREATE TRIGGER catalog_admin_history_no_update BEFORE UPDATE ON catalog_admin_history BEGIN SELECT RAISE(ABORT,'METADATA_IMMUTABLE'); END;
CREATE TRIGGER catalog_admin_history_no_delete BEFORE DELETE ON catalog_admin_history BEGIN SELECT RAISE(ABORT,'METADATA_IMMUTABLE'); END;
