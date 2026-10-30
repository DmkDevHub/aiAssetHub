ALTER TABLE creators ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1));
CREATE TRIGGER creators_no_delete BEFORE DELETE ON creators BEGIN SELECT RAISE(ABORT,'METADATA_IMMUTABLE'); END;
CREATE TRIGGER creators_delete_referenced BEFORE UPDATE OF deleted ON creators WHEN NEW.deleted=1 BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM asset_creator_links WHERE creator_id=NEW.id) OR EXISTS(SELECT 1 FROM package_creator_links WHERE creator_id=NEW.id) THEN RAISE(ABORT,'INVALID_REFERENCE') END;
END;
CREATE TRIGGER creators_deleted_readonly BEFORE UPDATE ON creators WHEN OLD.deleted=1 BEGIN SELECT RAISE(ABORT,'METADATA_IMMUTABLE'); END;
CREATE TRIGGER sources_no_delete BEFORE DELETE ON provenance_sources BEGIN SELECT RAISE(ABORT,'METADATA_IMMUTABLE'); END;
CREATE TRIGGER licenses_no_delete BEFORE DELETE ON provenance_licenses BEGIN SELECT RAISE(ABORT,'METADATA_IMMUTABLE'); END;
CREATE TRIGGER sources_owner_immutable BEFORE UPDATE OF asset_id,package_id ON provenance_sources WHEN NEW.asset_id IS NOT OLD.asset_id OR NEW.package_id IS NOT OLD.package_id BEGIN SELECT RAISE(ABORT,'INVALID_REFERENCE'); END;
CREATE TRIGGER licenses_owner_immutable BEFORE UPDATE OF asset_id,package_id ON provenance_licenses WHEN NEW.asset_id IS NOT OLD.asset_id OR NEW.package_id IS NOT OLD.package_id BEGIN SELECT RAISE(ABORT,'INVALID_REFERENCE'); END;
CREATE TRIGGER evidence_no_update BEFORE UPDATE ON license_evidence BEGIN SELECT RAISE(ABORT,'INVALID_REFERENCE'); END;
