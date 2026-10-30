CREATE TABLE provenance_licenses (
 id TEXT PRIMARY KEY, asset_id TEXT REFERENCES assets(id), package_id TEXT REFERENCES asset_packages(id),
 value_json TEXT NOT NULL CHECK(json_valid(value_json)), revision INTEGER NOT NULL CHECK(revision>0),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 source_id TEXT GENERATED ALWAYS AS (json_extract(value_json,'$.source_id')) STORED REFERENCES provenance_sources(id),
 CHECK((asset_id IS NULL)!=(package_id IS NULL))
);
CREATE INDEX licenses_asset ON provenance_licenses(asset_id,id);
CREATE INDEX licenses_package ON provenance_licenses(package_id,id);
CREATE TRIGGER license_source_owner_insert BEFORE INSERT ON provenance_licenses WHEN NEW.source_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM provenance_sources s WHERE s.id=NEW.source_id AND s.enabled=1 AND s.asset_id IS NEW.asset_id AND s.package_id IS NEW.package_id) THEN RAISE(ABORT,'INVALID_REFERENCE') END;
END;
CREATE TRIGGER license_source_owner_update BEFORE UPDATE OF value_json ON provenance_licenses WHEN NEW.source_id IS NOT OLD.source_id AND NEW.source_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM provenance_sources s WHERE s.id=NEW.source_id AND s.enabled=1 AND s.asset_id IS NEW.asset_id AND s.package_id IS NEW.package_id) THEN RAISE(ABORT,'INVALID_REFERENCE') END;
END;
CREATE TABLE license_evidence (
 license_id TEXT NOT NULL REFERENCES provenance_licenses(id), file_id TEXT NOT NULL REFERENCES asset_files(id),
 label TEXT NOT NULL CHECK(length(label)<=64), PRIMARY KEY(license_id,file_id)
);
CREATE TRIGGER evidence_owner_insert BEFORE INSERT ON license_evidence BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM provenance_licenses r JOIN asset_file_members m ON m.file_id=NEW.file_id
 WHERE r.id=NEW.license_id AND (m.asset_id=r.asset_id OR EXISTS(SELECT 1 FROM asset_package_members p WHERE p.package_id=r.package_id AND p.asset_id=m.asset_id))) THEN RAISE(ABORT,'INVALID_REFERENCE') END;
END;
