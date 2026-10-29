CREATE TABLE asset_groups (
 id TEXT PRIMARY KEY, name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 128),
 description TEXT NOT NULL CHECK(length(description)<=512),
 parent_id TEXT REFERENCES asset_groups(id), revision INTEGER NOT NULL CHECK(revision>0)
);
CREATE TABLE asset_group_members (
 group_id TEXT NOT NULL REFERENCES asset_groups(id) ON DELETE CASCADE,
 asset_id TEXT NOT NULL REFERENCES assets(id), PRIMARY KEY(group_id,asset_id)
);
CREATE INDEX group_members_asset ON asset_group_members(asset_id,group_id);
CREATE TABLE asset_collection_versions (
 asset_id TEXT NOT NULL REFERENCES assets(id), kind TEXT NOT NULL CHECK(kind IN ('group','package')),
 revision INTEGER NOT NULL CHECK(revision>0), PRIMARY KEY(asset_id,kind)
);
CREATE TABLE collection_history (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL, entity_id TEXT NOT NULL,
 revision INTEGER NOT NULL, action TEXT NOT NULL, before_json TEXT NOT NULL CHECK(json_valid(before_json)),
 after_json TEXT NOT NULL CHECK(json_valid(after_json)), created_at TEXT NOT NULL
);
CREATE INDEX collection_history_entity ON collection_history(kind,entity_id,id);
CREATE TRIGGER collection_history_no_update BEFORE UPDATE ON collection_history BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER collection_history_no_delete BEFORE DELETE ON collection_history BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
