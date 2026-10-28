-- Derived local search only. No source reads, models, jobs or network.
CREATE VIEW asset_search_source AS
SELECT a.id AS asset_id, search_normalize(a.display_name || ' ' || coalesce(u.title_override,'') || ' ' || coalesce(u.description_override,'') || ' ' ||
 coalesce((SELECT group_concat(relative_path,' ') FROM asset_files WHERE asset_id=a.id),'') || ' ' ||
 coalesce((SELECT group_concat(t.label,' ') FROM asset_tags at JOIN tags t ON t.id=at.tag_id
 WHERE at.asset_id=a.id AND (at.source='user' OR at.analysis_result_id=ar.analysis_result_id)),'') || ' ' ||
 coalesce(r.description,'') || ' ' || coalesce(r.tags_json,'')) AS searchable_text
FROM assets a LEFT JOIN asset_user_annotations u ON u.asset_id=a.id
LEFT JOIN asset_active_results ar ON ar.asset_id=a.id LEFT JOIN analysis_results r ON r.id=ar.analysis_result_id;
CREATE VIRTUAL TABLE asset_fts USING fts5(searchable_text, content='search_documents', content_rowid='rowid', tokenize='unicode61');
-- Existing v1 search documents must be indexed before update triggers emit deletes.
INSERT INTO asset_fts(asset_fts) VALUES ('rebuild');
CREATE TRIGGER search_document_insert AFTER INSERT ON search_documents BEGIN
 INSERT INTO asset_fts(rowid,searchable_text) VALUES (new.rowid,new.searchable_text);
END;
CREATE TRIGGER search_document_delete AFTER DELETE ON search_documents BEGIN
 INSERT INTO asset_fts(asset_fts,rowid,searchable_text) VALUES ('delete',old.rowid,old.searchable_text);
END;
CREATE TRIGGER search_document_update AFTER UPDATE ON search_documents BEGIN
 INSERT INTO asset_fts(asset_fts,rowid,searchable_text) VALUES ('delete',old.rowid,old.searchable_text);
 INSERT INTO asset_fts(rowid,searchable_text) VALUES (new.rowid,new.searchable_text);
END;
CREATE TRIGGER search_sync_assets_insert AFTER INSERT ON assets BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (new.id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (new.id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_assets_update AFTER UPDATE ON assets BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (old.id,new.id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (old.id,new.id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_assets_delete AFTER DELETE ON assets BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (old.id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (old.id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_files_insert AFTER INSERT ON asset_files BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_files_update AFTER UPDATE ON asset_files BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_files_delete AFTER DELETE ON asset_files BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_user_annotations_insert AFTER INSERT ON asset_user_annotations BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_user_annotations_update AFTER UPDATE ON asset_user_annotations BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_user_annotations_delete AFTER DELETE ON asset_user_annotations BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_tags_insert AFTER INSERT ON asset_tags BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_tags_update AFTER UPDATE ON asset_tags BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_tags_delete AFTER DELETE ON asset_tags BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_active_results_insert AFTER INSERT ON asset_active_results BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_active_results_update AFTER UPDATE ON asset_active_results BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_asset_active_results_delete AFTER DELETE ON asset_active_results BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
 DELETE FROM search_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT asset_id FROM asset_search_source);
END;
CREATE TRIGGER search_sync_tag_label AFTER UPDATE OF label ON tags BEGIN
 INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE asset_id IN (SELECT asset_id FROM asset_tags WHERE tag_id=new.id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
END;
INSERT INTO search_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM asset_search_source WHERE 1
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=search_documents.version+1,updated_at=excluded.updated_at;
INSERT INTO asset_fts(asset_fts) VALUES ('rebuild');
