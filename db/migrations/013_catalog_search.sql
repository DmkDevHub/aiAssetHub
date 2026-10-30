-- Public semantic fields only; no contacts, source URLs, purchase records or evidence.
CREATE VIEW catalog_group_ancestors AS WITH RECURSIVE ancestors(child,parent) AS (
 SELECT id,id FROM asset_groups UNION SELECT a.child,g.parent_id FROM ancestors a JOIN asset_groups g ON g.id=a.parent WHERE g.parent_id IS NOT NULL
) SELECT child,parent FROM ancestors;
CREATE VIEW catalog_search_projection AS
SELECT a.id AS asset_id,search_normalize(base.searchable_text||' '||
 coalesce((SELECT group_concat(j.value,' ') FROM metadata_decisions d,json_each(d.value_json,'$.aliases') j WHERE d.asset_id=a.id AND d.field='basic_text'),'')||' '||
 coalesce((SELECT group_concat(t.ko||' '||t.en||' '||t.code||' '||t.aliases_json,' ') FROM asset_classification_selections s JOIN classification_terms t ON t.version=s.type_version AND t.axis='type' AND (s.primary_code=t.code OR s.primary_code LIKE t.code||'.%') WHERE s.asset_id=a.id),'')||' '||
 coalesce((SELECT group_concat(t.ko||' '||t.en||' '||t.code||' '||t.aliases_json,' ') FROM asset_classification_links m JOIN classification_terms t ON t.version=m.version AND t.axis=m.axis AND t.code=m.code WHERE m.asset_id=a.id),'')||' '||
 coalesce((SELECT group_concat(g.name,' ') FROM asset_group_members m JOIN catalog_group_ancestors p ON p.child=m.group_id JOIN asset_groups g ON g.id=p.parent WHERE m.asset_id=a.id),'')||' '||
 coalesce((SELECT group_concat(p.name||' '||p.version,' ') FROM asset_package_members m JOIN asset_packages p ON p.id=m.package_id WHERE m.asset_id=a.id AND p.enabled=1),'')||' '||
 coalesce((SELECT group_concat(c.name||' '||c.brand||' '||m.role,' ') FROM asset_creator_links m JOIN creators c ON c.id=m.creator_id WHERE m.asset_id=a.id),'')||' '||
 coalesce((SELECT group_concat(c.name||' '||c.brand||' '||m.role,' ') FROM asset_package_members p JOIN package_creator_links m ON m.package_id=p.package_id JOIN creators c ON c.id=m.creator_id WHERE p.asset_id=a.id),'')) AS searchable_text
FROM assets a JOIN asset_search_source base ON base.asset_id=a.id;
CREATE TABLE catalog_documents (asset_id TEXT PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,searchable_text TEXT NOT NULL,version INTEGER NOT NULL,updated_at TEXT NOT NULL);
CREATE VIRTUAL TABLE catalog_fts USING fts5(searchable_text,content='catalog_documents',content_rowid='rowid',tokenize='unicode61');
CREATE TRIGGER catalog_document_insert AFTER INSERT ON catalog_documents BEGIN
 INSERT INTO catalog_fts(rowid,searchable_text) VALUES (new.rowid,new.searchable_text);
END;
CREATE TRIGGER catalog_document_delete AFTER DELETE ON catalog_documents BEGIN
 INSERT INTO catalog_fts(catalog_fts,rowid,searchable_text) VALUES ('delete',old.rowid,old.searchable_text);
END;
CREATE TRIGGER catalog_document_update AFTER UPDATE ON catalog_documents BEGIN
 INSERT INTO catalog_fts(catalog_fts,rowid,searchable_text) VALUES ('delete',old.rowid,old.searchable_text);
 INSERT INTO catalog_fts(rowid,searchable_text) VALUES (new.rowid,new.searchable_text);
END;
INSERT INTO catalog_documents SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection;
CREATE TRIGGER catalog_sync_search_documents_insert AFTER INSERT ON search_documents BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_search_documents_update AFTER UPDATE ON search_documents BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_search_documents_delete AFTER DELETE ON search_documents BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_metadata_decisions_insert AFTER INSERT ON metadata_decisions BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_metadata_decisions_update AFTER UPDATE ON metadata_decisions BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_metadata_decisions_delete AFTER DELETE ON metadata_decisions BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_classification_selections_insert AFTER INSERT ON asset_classification_selections BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_classification_selections_update AFTER UPDATE ON asset_classification_selections BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_classification_selections_delete AFTER DELETE ON asset_classification_selections BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_classification_links_insert AFTER INSERT ON asset_classification_links BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_classification_links_update AFTER UPDATE ON asset_classification_links BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_classification_links_delete AFTER DELETE ON asset_classification_links BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_group_members_insert AFTER INSERT ON asset_group_members BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_group_members_update AFTER UPDATE ON asset_group_members BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_group_members_delete AFTER DELETE ON asset_group_members BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_package_members_insert AFTER INSERT ON asset_package_members BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_package_members_update AFTER UPDATE ON asset_package_members BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_package_members_delete AFTER DELETE ON asset_package_members BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_creator_links_insert AFTER INSERT ON asset_creator_links BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_creator_links_update AFTER UPDATE ON asset_creator_links BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id,new.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id,new.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_creator_links_delete AFTER DELETE ON asset_creator_links BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (old.asset_id)
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (old.asset_id) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_groups_insert AFTER INSERT ON asset_groups BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT DISTINCT m.asset_id FROM asset_group_members m JOIN catalog_group_ancestors p ON p.child=m.group_id WHERE p.parent IN (new.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT DISTINCT m.asset_id FROM asset_group_members m JOIN catalog_group_ancestors p ON p.child=m.group_id WHERE p.parent IN (new.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_groups_update AFTER UPDATE ON asset_groups BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT DISTINCT m.asset_id FROM asset_group_members m JOIN catalog_group_ancestors p ON p.child=m.group_id WHERE p.parent IN (old.id,new.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT DISTINCT m.asset_id FROM asset_group_members m JOIN catalog_group_ancestors p ON p.child=m.group_id WHERE p.parent IN (old.id,new.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_groups_delete AFTER DELETE ON asset_groups BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT DISTINCT m.asset_id FROM asset_group_members m JOIN catalog_group_ancestors p ON p.child=m.group_id WHERE p.parent IN (old.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT DISTINCT m.asset_id FROM asset_group_members m JOIN catalog_group_ancestors p ON p.child=m.group_id WHERE p.parent IN (old.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_packages_insert AFTER INSERT ON asset_packages BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (new.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (new.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_packages_update AFTER UPDATE ON asset_packages BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (old.id,new.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (old.id,new.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_asset_packages_delete AFTER DELETE ON asset_packages BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (old.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (old.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_creators_insert AFTER INSERT ON creators BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_creator_links WHERE creator_id IN (new.id) UNION SELECT p.asset_id FROM asset_package_members p JOIN package_creator_links c ON c.package_id=p.package_id WHERE c.creator_id IN (new.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_creator_links WHERE creator_id IN (new.id) UNION SELECT p.asset_id FROM asset_package_members p JOIN package_creator_links c ON c.package_id=p.package_id WHERE c.creator_id IN (new.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_creators_update AFTER UPDATE ON creators BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_creator_links WHERE creator_id IN (old.id,new.id) UNION SELECT p.asset_id FROM asset_package_members p JOIN package_creator_links c ON c.package_id=p.package_id WHERE c.creator_id IN (old.id,new.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_creator_links WHERE creator_id IN (old.id,new.id) UNION SELECT p.asset_id FROM asset_package_members p JOIN package_creator_links c ON c.package_id=p.package_id WHERE c.creator_id IN (old.id,new.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_creators_delete AFTER DELETE ON creators BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_creator_links WHERE creator_id IN (old.id) UNION SELECT p.asset_id FROM asset_package_members p JOIN package_creator_links c ON c.package_id=p.package_id WHERE c.creator_id IN (old.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_creator_links WHERE creator_id IN (old.id) UNION SELECT p.asset_id FROM asset_package_members p JOIN package_creator_links c ON c.package_id=p.package_id WHERE c.creator_id IN (old.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_tags_insert AFTER INSERT ON tags BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_tags WHERE tag_id IN (new.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_tags WHERE tag_id IN (new.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_tags_update AFTER UPDATE ON tags BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_tags WHERE tag_id IN (old.id,new.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_tags WHERE tag_id IN (old.id,new.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_tags_delete AFTER DELETE ON tags BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_tags WHERE tag_id IN (old.id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_tags WHERE tag_id IN (old.id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_package_creator_links_insert AFTER INSERT ON package_creator_links BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (new.package_id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (new.package_id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_package_creator_links_update AFTER UPDATE ON package_creator_links BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (old.package_id,new.package_id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (old.package_id,new.package_id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
CREATE TRIGGER catalog_sync_package_creator_links_delete AFTER DELETE ON package_creator_links BEGIN
 INSERT INTO catalog_documents(asset_id,searchable_text,version,updated_at)
 SELECT asset_id,searchable_text,1,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM catalog_search_projection WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (old.package_id))
 ON CONFLICT(asset_id) DO UPDATE SET searchable_text=excluded.searchable_text,version=catalog_documents.version+1,updated_at=excluded.updated_at WHERE catalog_documents.searchable_text IS NOT excluded.searchable_text;
 DELETE FROM catalog_documents WHERE asset_id IN (SELECT asset_id FROM asset_package_members WHERE package_id IN (old.package_id)) AND asset_id NOT IN (SELECT id FROM assets);
END;
