CREATE TABLE provenance_sources (
 id TEXT PRIMARY KEY, asset_id TEXT REFERENCES assets(id), package_id TEXT REFERENCES asset_packages(id),
 value_json TEXT NOT NULL CHECK(json_valid(value_json)), revision INTEGER NOT NULL CHECK(revision>0),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), CHECK((asset_id IS NULL)!=(package_id IS NULL))
);
CREATE INDEX sources_asset ON provenance_sources(asset_id,id);
CREATE INDEX sources_package ON provenance_sources(package_id,id);
