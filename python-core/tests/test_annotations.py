from pathlib import Path
import tempfile
import unittest
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.libraries import LibraryService, LibraryError
from ai_asset_hub_core.annotations import AnnotationService


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / '.artifacts' / 'annotation-tests'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'; self.source.mkdir()
        (self.source / '나무.png').write_bytes(b'original')
        self.db = Database(self.base / 'db.sqlite')
        library = LibraryService(self.db).register({'path':str(self.source)})['library']['id']
        AssetService(self.db).scan({'library_id':library})
        self.id = AssetService(self.db).list({})['items'][0]['id']
        self.service = AnnotationService(self.db)

    def tearDown(self):
        self.db.close(); self.temp.cleanup()

    def test_tags_normalize_delete_persist_without_jobs_or_source_writes(self):
        edit = lambda add, remove: self.service.tags({'asset_id':self.id,'add':add,'remove':remove})
        self.assertEqual(edit([' 숲 ', 'Forest', 'forest'], [])['tags'], ['forest','숲'])
        self.assertEqual(edit([], ['FOREST'])['tags'], ['숲'])
        self.db.close(); self.db = Database(self.base / 'db.sqlite')
        self.service = AnnotationService(self.db)
        self.assertEqual(self.service.get({'asset_id':self.id})['tags'], ['숲'])
        self.assertEqual((self.source / '나무.png').read_bytes(), b'original')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_invalid_tags_are_atomic(self):
        for value in [[''], ['x'*65], ['line\nbreak'], ['x']*33, [None]]:
            with self.assertRaises(LibraryError):
                self.service.tags({'asset_id':self.id,'add':value,'remove':[]})
        self.assertEqual(self.service.get({'asset_id':self.id})['tags'], [])

    def test_user_description_title_override_and_restore_preserve_source(self):
        self.service.save({'asset_id':self.id,'title':'별칭','description':'숲 설명'})
        self.assertEqual(AssetService(self.db).list({})['items'][0]['name'],'별칭')
        self.db.close(); self.db = Database(self.base / 'db.sqlite'); self.service = AnnotationService(self.db)
        self.assertEqual(self.service.get({'asset_id':self.id})['description'],'숲 설명')
        self.service.save({'asset_id':self.id,'title':'','description':''})
        self.assertEqual(AssetService(self.db).list({})['items'][0]['name'],'나무.png')
        with self.assertRaises(LibraryError): self.service.save({'asset_id':self.id,'title':'a'*129,'description':''})
        self.assertEqual((self.source/'나무.png').read_bytes(),b'original')

    def test_batch_tags_are_atomic_and_keep_unrelated_tags(self):
        from uuid import uuid4
        other=str(uuid4()); library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        self.db.connection.execute('INSERT INTO assets(id,library_root_id,display_name) VALUES (?,?,?)',(other,library,'other'))
        self.service.tags({'asset_id':self.id,'add':['keep'],'remove':[]})
        result=self.service.batch({'asset_ids':[self.id,other],'add':['숲'],'remove':[]})
        self.assertEqual(result,{'updated':2})
        self.assertEqual(self.service.get({'asset_id':self.id})['tags'],['keep','숲'])
        with self.assertRaises(LibraryError):
            self.service.batch({'asset_ids':[self.id,str(uuid4())],'add':['rollback'],'remove':['keep']})
        self.assertEqual(self.service.get({'asset_id':self.id})['tags'],['keep','숲'])
        self.service.batch({'asset_ids':[self.id,other],'add':[],'remove':['숲']})
        self.assertEqual(self.service.get({'asset_id':other})['tags'],[])

    def test_basic_text_aliases_survive_reopen_rescan_and_legacy_save(self):
        params = {'asset_id':self.id, 'title':'표시 나무', 'description':'사용자 설명',
                  'aliases':[' Tree ', 'ＴＲＥＥ', '숲 나무'], 'expected_revision':0}
        result = self.service.save(params)
        self.assertEqual(result['aliases'], ['Tree','숲 나무'])
        self.assertEqual(result['originalName'], '나무.png')
        self.assertEqual(result['revision'], 1)
        self.db.close(); self.db = Database(self.base / 'db.sqlite'); self.service = AnnotationService(self.db)
        library = self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id':library})
        self.assertEqual(self.service.get({'asset_id':self.id}), result)
        self.service.save({'asset_id':self.id,'title':'다른 표시명','description':'설명'})
        self.assertEqual(self.service.get({'asset_id':self.id})['aliases'], result['aliases'])
        self.assertEqual([p.name for p in self.source.iterdir()], ['나무.png'])
        self.assertEqual((self.source/'나무.png').read_bytes(), b'original')
        for table in ('analysis_jobs','analysis_runs','asset_embeddings','metadata_claims'):
            self.assertEqual(self.db.connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 0)

    def test_basic_text_input_limits_conflicts_and_atomic_rollback(self):
        import sqlite3
        params = {'asset_id':self.id,'title':'saved','description':'saved', 'aliases':['saved'],'expected_revision':0}
        saved = self.service.save(params)
        for aliases in (None, '', ['x']*17, ['x'*65], ['x'*63+str(i) for i in range(9)], ['bad\nline'], [None], ['\ud800']):
            with self.assertRaises(LibraryError): self.service.save({**params,'aliases':aliases,'expected_revision':1})
        for key,value in (('title','x'*129),('description','x'*1025),('title','secret\0'),('description','\ud800')):
            with self.assertRaises(LibraryError): self.service.save({**params,key:value,'expected_revision':1})
        for version in (0, True, -1, None, '1'):
            with self.assertRaisesRegex(LibraryError,'METADATA_CONFLICT'):
                self.service.save({**params,'title':'not saved','expected_revision':version})
        self.db.connection.execute("CREATE TRIGGER fixture_reject BEFORE UPDATE ON asset_user_annotations BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.Error): self.service.save({**params,'title':'rollback','expected_revision':1})
        self.assertEqual(self.service.get({'asset_id':self.id}), saved)
        self.assertEqual(self.db.connection.execute("SELECT count(*) FROM metadata_decision_history WHERE field='basic_text'").fetchone()[0],1)

    def test_basic_text_clear_limits_and_safe_application_errors(self):
        from ai_asset_hub_core.application import CoreApplication
        from uuid import uuid4
        service = CoreApplication(self.db)
        request = lambda params: service.handle({'request_id':str(uuid4()),'method':'asset.annotate','params':params})
        params={'asset_id':self.id,'title':'a'*128,'description':'설'*1024,'aliases':[str(i)+'x'*63 for i in range(8)],'expected_revision':0}
        self.assertTrue(request(params)['ok'])
        conflict=request({**params,'title':'PRIVATE draft'})
        self.assertEqual(conflict['error']['code'],'METADATA_CONFLICT')
        self.assertNotIn('PRIVATE',str(conflict))
        self.assertTrue(request({**params,'title':'','description':'','aliases':[],'expected_revision':1})['ok'])
        result=self.service.get({'asset_id':self.id})
        self.assertEqual((result['title'],result['description'],result['aliases']),('','',[]))
        self.assertEqual(AssetService(self.db).list({})['items'][0]['name'],'나무.png')
        for query in ('asset.annotate','asset.annotations'):
            response=service.handle({'request_id':str(uuid4()),'method':query,'params':{'asset_id':str(uuid4())}})
            self.assertFalse(response['ok'])

    def test_failed_reanalysis_keeps_completed_filter_and_ai_tags(self):
        from uuid import uuid4
        job, success, failed, result = [str(uuid4()) for _ in range(4)]
        db=self.db.connection
        db.execute("INSERT INTO analysis_jobs(id,request_id,scope_json,model_snapshot_json,requested_count,status,created_at,initiated_by) VALUES (?,?,'{}','{}',1,'completed','2026-10-28T00:00:00Z','fixture')",(job,str(uuid4())))
        db.execute("INSERT INTO analysis_job_items(job_id,asset_id,status) VALUES (?,?,'completed')",(job,self.id))
        for run,status,time in [(success,'completed','01'),(failed,'failed','02')]:
            db.execute("INSERT INTO analysis_runs(id,job_id,asset_id,model_snapshot_json,input_fingerprint,status,created_at) VALUES (?,?,?,'{}','fixture',?,?)",(run,job,self.id,status,'2026-10-28T00:00:'+time+'Z'))
        db.execute("INSERT INTO analysis_results(id,run_id,asset_id,description,tags_json,features_json,created_at) VALUES (?,?,?,'active forest','[]','{}','2026-10-28T00:00:01Z')",(result,success,self.id))
        db.execute('INSERT INTO asset_active_results VALUES (?,?,?)',(self.id,result,'fixture'))
        self.service.tags({'asset_id':self.id,'add':['shared'],'remove':[]})
        tag=db.execute("SELECT id FROM tags WHERE normalized_label='shared'").fetchone()[0]
        db.execute("INSERT INTO asset_tags VALUES (?,?,'ai',?)",(self.id,tag,result))
        self.service.tags({'asset_id':self.id,'add':[],'remove':['shared']})
        item=AssetService(self.db).list({})['items'][0]
        self.assertTrue(item['hasActiveResult'])
        self.assertEqual(item['lastAttemptState'],'failed')
        self.assertEqual(item['lastAnalysisAt'],'2026-10-28T00:00:01Z')
        self.assertEqual(item['userTags'],[])
        self.assertEqual(db.execute("SELECT count(*) FROM asset_tags WHERE source='ai'").fetchone()[0],1)
        from ai_asset_hub_core.search import SearchService
        self.assertEqual(SearchService(self.db).search({'query':'shared'})['ids'],[self.id])
        self.assertEqual(db.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],1)

    def test_new_queued_attempt_and_source_fingerprint_survive_reopen(self):
        import json
        from uuid import uuid4
        from ai_asset_hub_core.analysis_state import asset_state
        job=str(uuid4())
        self.db.connection.execute("INSERT INTO analysis_jobs(id,request_id,scope_json,model_snapshot_json,requested_count,status,created_at,initiated_by) VALUES (?,?,'{}','{}',1,'queued','2030-01-01','fixture')",(job,str(uuid4())))
        self.db.connection.execute("INSERT INTO analysis_job_items(job_id,asset_id,status) VALUES (?,?,'queued')",(job,self.id))
        self.assertEqual(asset_state(self.db.connection,self.id)['lastAttemptState'],'queued')
        self.db.close();self.db=Database(self.base/'db.sqlite')
        state=asset_state(self.db.connection,self.id)
        self.assertEqual(state['lastAttemptState'],'queued');self.assertFalse(state['hasActiveResult'])
        self.db.connection.execute("UPDATE asset_files SET sha256='fixture-hash'")
        (self.source/'나무.png').write_bytes(b'changed-original-fixture')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id':library})
        self.assertIsNone(self.db.connection.execute('SELECT sha256 FROM asset_files').fetchone()[0])
