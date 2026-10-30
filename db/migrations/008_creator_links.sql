CREATE TABLE asset_creator_links (
 asset_id TEXT NOT NULL REFERENCES assets(id), creator_id TEXT NOT NULL REFERENCES creators(id),
 role TEXT NOT NULL CHECK(role IN ('creator','producer','distributor')), PRIMARY KEY(asset_id,creator_id,role)
);
CREATE TABLE package_creator_links (
 package_id TEXT NOT NULL REFERENCES asset_packages(id), creator_id TEXT NOT NULL REFERENCES creators(id),
 role TEXT NOT NULL CHECK(role IN ('creator','producer','distributor')), PRIMARY KEY(package_id,creator_id,role)
);
CREATE TABLE asset_creator_revisions (asset_id TEXT PRIMARY KEY REFERENCES assets(id), revision INTEGER NOT NULL CHECK(revision>0));
CREATE TABLE package_creator_revisions (package_id TEXT PRIMARY KEY REFERENCES asset_packages(id), revision INTEGER NOT NULL CHECK(revision>0));
CREATE TABLE provenance_history (
 id TEXT PRIMARY KEY, subject_kind TEXT NOT NULL CHECK(subject_kind IN ('asset','package','creator')),
 subject_id TEXT NOT NULL, entity_id TEXT NOT NULL, field TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 action TEXT NOT NULL, before_json TEXT NOT NULL CHECK(json_valid(before_json)), after_json TEXT NOT NULL CHECK(json_valid(after_json)), created_at TEXT NOT NULL
);
CREATE INDEX provenance_history_subject ON provenance_history(subject_kind,subject_id,created_at,id);
CREATE TRIGGER provenance_history_no_update BEFORE UPDATE ON provenance_history BEGIN SELECT RAISE(ABORT,'METADATA_IMMUTABLE'); END;
CREATE TRIGGER provenance_history_no_delete BEFORE DELETE ON provenance_history BEGIN SELECT RAISE(ABORT,'METADATA_IMMUTABLE'); END;
