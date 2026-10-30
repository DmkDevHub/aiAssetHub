import json
import shutil
import sqlite3
import hashlib
import unittest
from pathlib import Path
from uuid import uuid4
import test_annotations
import test_analysis
from ai_asset_hub_core.database import Database,DatabaseFailure,migration_directory
from ai_asset_hub_core.metadata_store import MetadataStore
from ai_asset_hub_core.metadata_values import MetadataError
from ai_asset_hub_core.taxonomy import default_taxonomy
from ai_asset_hub_core.classification_axes import default_facets


class MetadataStoreTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def test_seed_snapshots_match_contracts_and_are_immutable(self):
        for contract in (default_taxonomy().contract(),default_facets().contract()):
            stored=self.db.connection.execute('SELECT payload_json FROM classification_dictionaries WHERE version=?',(contract['version'],)).fetchone()[0]
            self.assertEqual(json.loads(stored),contract)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM classification_terms').fetchone()[0],103)
        for sql in ('DELETE FROM classification_terms','UPDATE classification_dictionaries SET kind=kind'):
            with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute(sql)

    def test_multi_file_membership_preserves_physical_owners_and_reads(self):
        from ai_asset_hub_core.assets import AssetService
        (self.source/'other.png').write_bytes(b'test-owned dependency')
        library=self.db.connection.execute('SELECT library_root_id FROM assets WHERE id=?',(self.id,)).fetchone()[0]
        AssetService(self.db).scan({'library_id':library})
        file,owner=self.db.connection.execute('SELECT id,asset_id FROM asset_files WHERE asset_id!=?',(self.id,)).fetchone()
        self.db.connection.execute("INSERT INTO asset_file_members VALUES (?,?,'dependency')",(self.id,file))
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_file_members WHERE asset_id=?',(self.id,)).fetchone()[0],2)
        self.assertEqual(self.db.connection.execute('SELECT asset_id FROM asset_files WHERE id=?',(file,)).fetchone()[0],owner)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM assets').fetchone()[0],2)
        MetadataStore(self.db).propose(self.id,'dependency_size','parser',21,file,'fixture.v1')
        self.assertEqual((self.source/'other.png').read_bytes(),b'test-owned dependency')

    def test_persistent_claims_clear_adopt_conflict_and_history(self):
        store=MetadataStore(self.db);file=self.db.connection.execute('SELECT id FROM asset_files').fetchone()[0]
        observed=store.propose(self.id,'description','parser','observed',file,'fixture.v1')
        test_analysis.AnalysisTests.history(self,self.id,'completed',True)
        result=self.db.connection.execute('SELECT id FROM analysis_results').fetchone()[0]
        suggested=store.propose(self.id,'description','ai','proposal',result,'fixture.v1')
        self.assertEqual(store.effective(self.id,'description')['value'],'observed')
        store.decide(self.id,'description','set',value='user',expected_revision=0,confirmed=True)
        store.propose(self.id,'description','ai','new proposal',result,'fixture.v1')
        self.assertEqual(store.effective(self.id,'description')['value'],'user')
        store.decide(self.id,'description','clear',expected_revision=1,confirmed=True)
        self.db.close();self.db=Database(self.base/'db.sqlite');store=MetadataStore(self.db)
        self.assertEqual(store.effective(self.id,'description')['status'],'cleared')
        with self.assertRaises(MetadataError):store.decide(self.id,'description','adopt',claim_id=suggested,expected_revision=1,confirmed=True)
        store.decide(self.id,'description','adopt',claim_id=suggested,expected_revision=2,confirmed=True)
        self.assertEqual(store.effective(self.id,'description')['value'],'proposal')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM metadata_decision_history').fetchone()[0],3)
        self.assertEqual(json.loads(self.db.connection.execute('SELECT before_json FROM metadata_decision_history ORDER BY id LIMIT 1').fetchone()[0])['value'],'observed')
        for sql in ('DELETE FROM metadata_claims','DELETE FROM metadata_decisions','UPDATE metadata_decision_history SET action=action'):
            with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute(sql)
        with self.assertRaises(MetadataError):store.propose(self.id,'description','ai','fake',str(uuid4()),'fixture.v1')

    def test_classification_references_retirement_and_rollback(self):
        store=MetadataStore(self.db)
        value=store.classify(self.id,primary='A02.01.01',navigation=['A02','A09.01'],facets={'style':['Pixel Art'],'engine':['Unity']},expected_revision=0,confirmed=True)
        self.assertEqual(value['type']['navigation'],['A09.01'])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_classification_links').fetchone()[0],3)
        with self.assertRaises(ValueError):store.retire_facet('style.pixel',new_version='asset-facets.v2')
        changed=store.retire_facet('style.pixel',new_version='asset-facets.v2',replacement='style.cartoon',confirmed=True)
        self.assertEqual(changed['affectedAssetCount'],1)
        self.assertEqual(self.db.connection.execute("SELECT active FROM classification_terms WHERE version='asset-facets.v1' AND code='style.pixel'").fetchone()[0],1)
        before=self.db.connection.execute('SELECT * FROM asset_classification_links').fetchall()
        with self.assertRaises(MetadataError):store.classify(self.id,primary='A01',expected_revision=0,confirmed=True)
        self.assertEqual(before,self.db.connection.execute('SELECT * FROM asset_classification_links').fetchall())
        with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute("INSERT INTO asset_classification_links VALUES (?,?,?,?)",(self.id,'asset-facets.v1','style','engine.unity'))
        with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute("INSERT INTO asset_classification_links VALUES (?,?,?,?)",(self.id,'asset-facets.v2','style','style.pixel'))
        with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute("INSERT INTO asset_classification_links VALUES (?,?,?,?)",(self.id,'asset-types.v1','type','A02'))
        with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute("INSERT INTO classification_terms VALUES ('asset-types.v1','type','type','A01.99','A01','가짜','Fake','[]',1,NULL)")
        with self.assertRaises(ValueError):store.classify(self.id,facets={'style':['Pixel Art']},facet_version='asset-facets.v2',expected_revision=1,confirmed=True)
        store.classify(self.id,primary='A02',facets={'style':['Cartoon']},facet_version='asset-facets.v2',expected_revision=1,confirmed=True)
        self.assertEqual(self.db.connection.execute("SELECT version,code FROM asset_classification_links WHERE axis='style'").fetchone(),('asset-facets.v2','style.cartoon'))

    def v3(self):
        self.db.close();scripts=self.base/'v3-migrations';scripts.mkdir()
        for source in sorted(migration_directory().glob('*.sql'))[:3]:shutil.copyfile(source,scripts/source.name)
        self.db=Database(self.base/'v3.sqlite',migrations=scripts)
        from ai_asset_hub_core.libraries import LibraryService
        from ai_asset_hub_core.assets import AssetService
        library=LibraryService(self.db).register({'path':str(self.source)})['library']['id'];AssetService(self.db).scan({'library_id':library})
        self.id=AssetService(self.db).list({})['items'][0]['id']
        # Historical v3 fixture: seed the old schema without the current v4 service.
        tag = str(uuid4())
        self.db.connection.execute('INSERT INTO tags VALUES (?,?,?)',(tag,'보존 태그','보존 태그'))
        self.db.connection.execute("INSERT INTO asset_tags(asset_id,tag_id,source) VALUES (?,?,'user')",(self.id,tag))
        self.db.connection.execute('INSERT INTO asset_user_annotations VALUES (?,?,?,?)',(self.id,'사용자 표시명','사용자 메모','fixture'))
        test_analysis.AnalysisTests.history(self,self.id,'completed',True)
        test_analysis.AnalysisTests.history(self,self.id,'failed',timestamp='2026-10-28T00:00:01Z')
        self.db.connection.execute("UPDATE asset_files SET sha256='fixture'")
        result=self.db.connection.execute('SELECT id FROM analysis_results').fetchone()[0]
        self.db.connection.execute("INSERT INTO asset_embeddings VALUES (?,?,?,3,?,?,'fixture')",(self.id,result,'fixture-version',b'preserved-vector','fixture'))
        return scripts

    def test_v3_upgrade_preserves_ids_history_fts_vectors_and_original(self):
        self.v3();tables=('assets','asset_files','tags','asset_tags','asset_user_annotations','analysis_jobs','analysis_job_items','analysis_runs','analysis_results','asset_active_results','search_documents','asset_embeddings')
        columns={t:','.join(r[1] for r in self.db.connection.execute('PRAGMA table_info('+t+')')) for t in tables}
        before={t:self.db.connection.execute('SELECT '+columns[t]+' FROM '+t+' ORDER BY rowid').fetchall() for t in tables}
        original=hashlib.sha256((self.source/'나무.png').read_bytes()).hexdigest()
        self.db.close();self.db=Database(self.base/'v3.sqlite')
        self.assertEqual(self.db.health()['schema_version'],len(list(migration_directory().glob('*.sql'))));self.assertTrue(self.db.backup_path.exists())
        self.assertEqual(before,{t:self.db.connection.execute('SELECT '+columns[t]+' FROM '+t+' ORDER BY rowid').fetchall() for t in tables})
        self.assertEqual(self.db.connection.execute('SELECT enabled,revision FROM tags').fetchone(),(1,1))
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_file_members').fetchone()[0],1)
        self.db.connection.execute("INSERT INTO asset_fts(asset_fts,rank) VALUES ('integrity-check',1)")
        self.assertEqual(original,hashlib.sha256((self.source/'나무.png').read_bytes()).hexdigest())
        backup=sqlite3.connect(self.db.backup_path)
        try:self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0],3)
        finally:backup.close()

    def test_failed_v4_migration_leaves_v3_data_and_no_partial_tables(self):
        scripts=self.v3();original=self.db.connection.execute('SELECT * FROM assets').fetchall();self.db.close()
        actual=migration_directory()/'004_metadata_foundation.sql'
        (scripts/actual.name).write_text(actual.read_text(encoding='utf-8')+'\nINVALID SQL;\n',encoding='utf-8')
        with self.assertRaises(DatabaseFailure):Database(self.base/'v3.sqlite',migrations=scripts)
        (scripts/actual.name).unlink();self.db=Database(self.base/'v3.sqlite',migrations=scripts)
        self.assertEqual(self.db.health()['schema_version'],3)
        self.assertEqual(self.db.connection.execute('SELECT * FROM assets').fetchall(),original)
        self.assertIsNone(self.db.connection.execute("SELECT name FROM sqlite_master WHERE name='metadata_claims'").fetchone())
