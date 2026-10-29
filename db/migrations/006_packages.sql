CREATE TABLE asset_packages (
 id TEXT PRIMARY KEY, name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 128),
 description TEXT NOT NULL CHECK(length(description)<=512), unit TEXT NOT NULL CHECK(unit IN ('distribution','purchase')),
 version TEXT NOT NULL CHECK(length(version)<=64), purchase_json TEXT NOT NULL CHECK(json_valid(purchase_json)),
 defaults_json TEXT NOT NULL CHECK(json_valid(defaults_json)), revision INTEGER NOT NULL CHECK(revision>0),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
CREATE TABLE asset_package_members (
 package_id TEXT NOT NULL REFERENCES asset_packages(id), asset_id TEXT NOT NULL REFERENCES assets(id),
 PRIMARY KEY(package_id,asset_id)
);
CREATE INDEX package_members_asset ON asset_package_members(asset_id,package_id);
CREATE TABLE package_purchase_snapshots (
 package_id TEXT NOT NULL REFERENCES asset_packages(id), asset_id TEXT NOT NULL REFERENCES assets(id),
 record_json TEXT NOT NULL CHECK(json_valid(record_json)), created_at TEXT NOT NULL,
 PRIMARY KEY(package_id,asset_id)
);
CREATE TRIGGER package_purchase_snapshots_no_update BEFORE UPDATE ON package_purchase_snapshots BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
CREATE TRIGGER package_purchase_snapshots_no_delete BEFORE DELETE ON package_purchase_snapshots BEGIN
 SELECT RAISE(ABORT,'METADATA_IMMUTABLE');
END;
