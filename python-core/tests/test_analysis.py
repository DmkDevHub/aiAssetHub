import unittest
from uuid import uuid4
import test_annotations
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.analysis_plan import AnalysisPlan
from ai_asset_hub_core.libraries import LibraryError


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        test_annotations.AnnotationTests.setUp(self)
        import json
        from datetime import datetime,timezone
        from ai_asset_hub_core.models import ModelService
        service=ModelService(self.db)
        self.model=service.register({'provider_name':'Ollama','kind':'local','model_id':'fixture-only-model','modalities':['image']})['id']
        self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps({'verified':True,'modalities':['image'],'checkedAt':datetime.now(timezone.utc).isoformat()}),self.model))
        service.policy({'id':self.model,'enabled':True,'allow_external':False,'allow_paid':False,'budget_usd':'0','max_requests':1000})
    tearDown=test_annotations.AnnotationTests.tearDown

    def params(self, **updates):
        result={'mode':'all','scope':'all','library_id':None,'folder_parts':[],'selected_ids':[],'model_id':self.model}
        result.update(updates);return result

    def test_versioned_support_contract_is_read_only_and_does_not_guess_unknown_formats(self):
        from unittest.mock import patch
        from ai_asset_hub_core.analysis_contract import input_support
        for name in ('audio.wav','unknown.mystery'):(self.source/name).write_bytes(b'fixture')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id':library})
        with patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('no inference')):
            preview=AnalysisPlan(self.db).preview(self.params())
        self.assertEqual((preview['eligibleCount'],preview['unsupportedCount'],preview['unknownFormatCount']),(1,2,1))
        self.assertEqual(input_support('FILE.PNG'),'supported')
        self.assertEqual(input_support('file.wav'),'unsupported')
        self.assertEqual(input_support('file'),'unknown')
        contract=preview['snapshot']['analysisContract']
        self.assertEqual(len(contract['supportMatrix']),14)
        self.assertEqual(contract['supportMatrix'][0]['structuredClassification'],'image-proposals')
        self.assertEqual(contract['multiFileAnalysis'],'unsupported')
        self.assertFalse(contract['transfer']['originalFile'])
        self.assertEqual(len(contract['reviewInputFingerprint']),64)
        self.assertTrue(contract['dictionaries'])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        self.assertEqual(AnalysisPlan(self.db).preview(self.params())['planToken'],preview['planToken'])

    def test_contract_and_dictionary_changes_invalidate_review_and_persist_on_explicit_start(self):
        import json
        from unittest.mock import patch
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        preview=AnalysisPlan(self.db).preview(self.params())
        request={'plan':self.params(),'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False}
        with patch('ai_asset_hub_core.analysis_contract.OUTPUT_VERSION','fixture-next-version'):
            with self.assertRaisesRegex(LibraryError,'ANALYSIS_PLAN_CHANGED'):AnalysisJobs(self.db).start(request)
        with patch('ai_asset_hub_core.inference.PROMPT','fixture-new-prompt'):
            with self.assertRaisesRegex(LibraryError,'ANALYSIS_PLAN_CHANGED'):AnalysisJobs(self.db).start(request)
        self.db.connection.execute("INSERT INTO classification_dictionaries VALUES ('fixture-new-version','type',?)",(json.dumps({'version':'fixture-new-version','categories':[]}),))
        with self.assertRaisesRegex(LibraryError,'ANALYSIS_PLAN_CHANGED'):AnalysisJobs(self.db).start(request)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        preview=AnalysisPlan(self.db).preview(self.params());request['plan_token']=preview['planToken']
        job=AnalysisJobs(self.db).start(request)['jobId']
        stored=json.loads(self.db.connection.execute('SELECT model_snapshot_json FROM analysis_jobs WHERE id=?',(job,)).fetchone()[0])
        self.assertEqual(stored['analysisContract'],preview['snapshot']['analysisContract'])
        self.assertEqual(stored['profileVersion'],preview['snapshot']['profileVersion'])

    def history(self, identifier, status, active=False, timestamp='2026-10-28T00:00:00Z'):
        job,run,result=[str(uuid4()) for _ in range(3)];db=self.db.connection
        db.execute("INSERT INTO analysis_jobs(id,request_id,scope_json,model_snapshot_json,requested_count,status,created_at,initiated_by) VALUES (?,?,'{}','{}',1,?,?,'fixture')",(job,str(uuid4()),status,timestamp))
        db.execute('INSERT INTO analysis_job_items(job_id,asset_id,status) VALUES (?,?,?)',(job,identifier,status))
        db.execute("INSERT INTO analysis_runs(id,job_id,asset_id,model_snapshot_json,input_fingerprint,status,created_at) VALUES (?,?,?,'{}','fixture',?,?)",(run,job,identifier,status,timestamp))
        if active:
            db.execute("INSERT INTO analysis_results(id,run_id,asset_id,description,tags_json,features_json,created_at) VALUES (?,?,?,'fixture successful','[]','{}',?)",(result,run,identifier,timestamp))
            db.execute('INSERT INTO asset_active_results VALUES (?,?,?)',(identifier,result,timestamp))

    def test_queued_job_refuses_changed_contract_before_inference(self):
        import time
        from unittest.mock import patch
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        from ai_asset_hub_core.analysis_engine import AnalysisEngine
        preview=AnalysisPlan(self.db).preview(self.params())
        job=AnalysisJobs(self.db).start({'plan':self.params(),'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
        engine=AnalysisEngine(self.db)
        with patch('ai_asset_hub_core.analysis_contract.OUTPUT_VERSION','fixture-changed'),patch('ai_asset_hub_core.inference.infer') as inference:
            engine.launch(job)
            deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
            engine.close()
            inference.assert_not_called()
        status=AnalysisJobs(self.db).status({'job_id':job})
        self.assertEqual(status['failed'],1)
        self.assertEqual(status['errors'][0]['code'],'ANALYSIS_PLAN_CHANGED')

    def test_modes_count_success_and_last_failure_independently_without_creating_jobs(self):
        (self.source/'other.txt').write_text('fixture')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id':library})
        other=self.db.connection.execute('SELECT id FROM assets WHERE id!=?',(self.id,)).fetchone()[0]
        self.history(self.id,'completed',True)
        self.history(self.id,'failed',timestamp='2026-10-28T00:00:01Z')
        plan=AnalysisPlan(self.db)
        for mode,count in [('all',2),('unanalyzed',1),('completed',1),('failed',1)]:
            self.assertEqual(plan.preview(self.params(mode=mode))['targetCount'],count)
        self.assertEqual(plan.preview(self.params(mode='selected',selected_ids=[other]))['targetCount'],1)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],2)
        with self.assertRaises(LibraryError):plan.preview(self.params(mode='selected',selected_ids=[str(uuid4())]))

    def test_folder_library_and_selection_scopes_intersect_without_prefix_collisions(self):
        for folder in ('tree','treehouse'):
            path=self.source/folder;path.mkdir();(path/'asset.png').write_bytes(b'fixture')
        nested=self.source/'tree'/'child';nested.mkdir();(nested/'nested.png').write_bytes(b'fixture')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0]
        AssetService(self.db).scan({'library_id':library});plan=AnalysisPlan(self.db)
        self.assertEqual(plan.preview(self.params(scope='folder',library_id=library,folder_parts=['tree']))['targetCount'],2)
        self.assertEqual(plan.preview(self.params(scope='library',library_id=library))['targetCount'],4)
        self.assertEqual(plan.preview(self.params(scope='folder',library_id=library,folder_parts=['tree'],mode='selected',selected_ids=[self.id]))['targetCount'],0)
        with self.assertRaises(LibraryError):plan.preview(self.params(scope='folder',library_id=library,folder_parts=['..']))
        with self.assertRaises(LibraryError):plan.preview(self.params(scope='library',library_id=str(uuid4())))

    def test_start_requires_matching_review_is_idempotent_and_reserves_atomically(self):
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        from ai_asset_hub_core.model_policy import BudgetPolicy
        plan=self.params();preview=AnalysisPlan(self.db).preview(plan)
        request={'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False}
        jobs=AnalysisJobs(self.db)
        (self.source/'나무.png').write_bytes(b'changed fixture')
        with self.assertRaises(LibraryError):jobs.start(request)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        request['plan_token']=AnalysisPlan(self.db).preview(plan)['planToken']
        result=jobs.start(request);self.assertFalse(result['reused'])
        self.assertEqual(jobs.start(request),{'jobId':result['jobId'],'reused':True})
        self.assertEqual(BudgetPolicy(self.db.connection).read(self.model)['requestsUsed'],1)
        self.assertEqual(self.db.connection.execute('SELECT status FROM analysis_jobs').fetchone()[0],'queued')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_runs').fetchone()[0],0)

    def test_paid_job_requires_bounded_pricing_and_fresh_per_job_approvals(self):
        import json
        from datetime import datetime,timezone
        from unittest.mock import patch
        from ai_asset_hub_core.models import ModelService
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        service=ModelService(self.db)
        identifier=service.register({'provider_name':'OpenRouter','kind':'external','model_id':'fixture/paid','modalities':['image']})['id']
        caps={'verified':True,'modalities':['image'],'checkedAt':datetime.now(timezone.utc).isoformat(),'authentication':'authenticated','costClass':'paid','pricing':{'prompt':'0.000001','completion':'0.000001','image':'0.001','request':'0'}}
        self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps(caps),identifier))
        with patch('ai_asset_hub_core.credentials.Vault.read',return_value='fixture-key'),patch('ai_asset_hub_core.providers.metadata',side_effect=AssertionError('no network')):
            service.policy({'id':identifier,'enabled':True,'allow_external':True,'allow_paid':True,'budget_usd':'1','max_requests':5})
            plan=self.params(model_id=identifier)
            with self.assertRaises(LibraryError):AnalysisPlan(self.db).preview(plan)
            caps['contextLength']=4096
            self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps(caps),identifier))
            preview=AnalysisPlan(self.db).preview(plan)
            request={'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':True}
            with self.assertRaises(LibraryError):AnalysisJobs(self.db).start(request)
            request.update(confirm_external=True,confirm_paid=False)
            with self.assertRaises(LibraryError):AnalysisJobs(self.db).start(request)
            self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
            request['confirm_paid']=True
            self.assertTrue(AnalysisJobs(self.db).start(request)['jobId'])

    def test_worker_persists_a_real_decoded_image_result_and_keeps_user_metadata(self):
        import json,time
        from unittest.mock import patch
        from PIL import Image
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        from ai_asset_hub_core.analysis_engine import AnalysisEngine
        from ai_asset_hub_core.annotations import AnnotationService
        from ai_asset_hub_core.analysis_results import AssetAnalysis
        from ai_asset_hub_core.analysis_state import asset_state
        Image.new('RGB',(64,64),'red').save(self.source/'나무.png');before=(self.source/'나무.png').read_bytes()
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0];AssetService(self.db).scan({'library_id':library})
        caps=json.loads(self.db.connection.execute('SELECT capabilities_json FROM model_registry WHERE id=?',(self.model,)).fetchone()[0]);caps['metadataVersion']='a'*64
        self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps(caps),self.model))
        AnnotationService(self.db).tags({'asset_id':self.id,'add':['mine'],'remove':[]})
        plan=self.params();preview=AnalysisPlan(self.db).preview(plan)
        job=AnalysisJobs(self.db).start({'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
        engine=AnalysisEngine(self.db)
        with patch('ai_asset_hub_core.providers.inspect_local',return_value={'status':'available','metadataVersion':'a'*64}),patch('ai_asset_hub_core.inference.infer',return_value=({'description':'Fixture red image','tags':['red'],'suggestions':{'primary':'A01','roles':['role.environment'],'styles':['style.pixel'],'colors':['red']}},{'providerRequestAttempted':True})):
            engine.launch(job)
            deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
            engine.close()
        self.assertEqual(AnalysisJobs(self.db).status({'job_id':job})['succeeded'],1)
        self.assertEqual(AssetAnalysis(self.db).get({'asset_id':self.id})['active']['description'],'Fixture red image')
        self.assertEqual(AnnotationService(self.db).get({'asset_id':self.id})['tags'],['mine'])
        self.assertFalse(asset_state(self.db.connection,self.id)['analysisStale'])
        features=AssetAnalysis(self.db).get({'asset_id':self.id})['active']['features']
        self.assertEqual(features['technical']['width'],64)
        self.assertFalse(features['technical']['hasTransparentPixels'])
        self.assertEqual(features['suggestions']['primary'],'A01')
        self.assertEqual((self.source/'나무.png').read_bytes(),before)

    def test_batch_queue_reports_measured_counts_and_continues_after_item_failure(self):
        import json,time,threading
        from unittest.mock import patch
        from PIL import Image
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        from ai_asset_hub_core.analysis_engine import AnalysisEngine
        for name in ('나무.png','second.png','third.png'):Image.new('RGB',(16,16),'blue').save(self.source/name)
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0];AssetService(self.db).scan({'library_id':library})
        caps=json.loads(self.db.connection.execute('SELECT capabilities_json FROM model_registry WHERE id=?',(self.model,)).fetchone()[0]);caps['metadataVersion']='a'*64
        self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps(caps),self.model))
        plan=self.params();preview=AnalysisPlan(self.db).preview(plan);jobs=AnalysisJobs(self.db)
        job=jobs.start({'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
        entered=threading.Event();release=threading.Event();calls=[]
        def inference(*args):
            calls.append(1)
            if len(calls)==1:entered.set();release.wait(3)
            if len(calls)==2:raise LibraryError('API_RATE_LIMIT')
            return {'description':'Fixture batch image','tags':['blue']},{'providerRequestAttempted':True}
        engine=AnalysisEngine(self.db)
        with patch('ai_asset_hub_core.providers.inspect_local',return_value={'status':'available','metadataVersion':'a'*64}),patch('ai_asset_hub_core.inference.infer',side_effect=inference):
            engine.launch(job);self.assertTrue(entered.wait(3))
            status=jobs.status({'job_id':job},engine.active(job));self.assertEqual(status['processed'],0);self.assertEqual(status['total'],3)
            release.set();deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
            engine.close()
        status=jobs.status({'job_id':job})
        self.assertEqual((status['processed'],status['succeeded'],status['failed']),(3,2,1))
        self.assertEqual(status['status'],'failed');self.assertEqual(status['errors'][0]['code'],'API_RATE_LIMIT')
        self.assertEqual(len(calls),3);self.assertEqual(jobs.list({})['items'][0]['id'],job)

    def test_orphan_cancel_and_retry_require_explicit_new_review(self):
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        jobs=AnalysisJobs(self.db);plan=self.params();preview=AnalysisPlan(self.db).preview(plan)
        job=jobs.start({'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
        self.assertTrue(jobs.status({'job_id':job})['needsRecovery'])
        with self.assertRaises(LibraryError):jobs.retry_plan({'job_id':job})
        self.assertEqual(jobs.cancel_orphan({'job_id':job})['status'],'canceled')
        retry=jobs.retry_plan({'job_id':job});self.assertEqual(retry['plan'],plan);self.assertTrue(retry['requiresReview'])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],1)
        self.assertEqual(jobs.status({'job_id':job})['canceled'],1)
        self.assertFalse(jobs.cancel_orphan({'job_id':job})['cancelRequested'])

    def test_active_cancel_stops_queue_and_records_canceled_attempt(self):
        import json,time,threading
        from unittest.mock import patch
        from PIL import Image
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        from ai_asset_hub_core.analysis_engine import AnalysisEngine
        for name in ('나무.png','second.png'):Image.new('RGB',(16,16),'red').save(self.source/name)
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0];AssetService(self.db).scan({'library_id':library})
        caps=json.loads(self.db.connection.execute('SELECT capabilities_json FROM model_registry WHERE id=?',(self.model,)).fetchone()[0]);caps['metadataVersion']='a'*64
        self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps(caps),self.model))
        plan=self.params();preview=AnalysisPlan(self.db).preview(plan);jobs=AnalysisJobs(self.db)
        job=jobs.start({'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
        entered=threading.Event();calls=[]
        def inference(*args):
            calls.append(1);entered.set();args[2].wait(3);raise LibraryError('USER_CANCELED')
        engine=AnalysisEngine(self.db)
        with patch('ai_asset_hub_core.providers.inspect_local',return_value={'status':'available','metadataVersion':'a'*64}),patch('ai_asset_hub_core.inference.infer',side_effect=inference):
            engine.launch(job);self.assertTrue(entered.wait(3));self.assertTrue(engine.cancel(job));engine.close()
        status=jobs.status({'job_id':job});self.assertEqual(status['status'],'canceled');self.assertEqual(status['canceled'],2)
        self.assertEqual(len(calls),1);self.assertEqual(self.db.connection.execute('SELECT count(*) FROM asset_active_results').fetchone()[0],0)
        self.assertEqual(self.db.connection.execute('SELECT status FROM analysis_runs').fetchone()[0],'canceled')

    def test_history_is_paged_append_only_and_failure_preserves_active_success(self):
        import sqlite3
        from ai_asset_hub_core.analysis_results import AssetAnalysis
        self.history(self.id,'completed',True)
        self.history(self.id,'failed',timestamp='2026-10-28T00:00:01Z')
        service=AssetAnalysis(self.db);first=service.history({'asset_id':self.id})
        self.assertEqual(first['items'][0]['status'],'failed');self.assertIsNone(first['items'][0]['description'])
        second=service.history({'asset_id':self.id,'after_id':first['next_cursor']})
        self.assertEqual(second['items'][0]['description'],'fixture successful');self.assertTrue(second['items'][0]['active'])
        self.assertEqual(service.get({'asset_id':self.id})['active']['description'],'fixture successful')
        for sql in ("DELETE FROM analysis_results","DELETE FROM analysis_runs","UPDATE analysis_runs SET status='running'","UPDATE analysis_jobs SET model_snapshot_json='{}'"):
            with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute(sql)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_results').fetchone()[0],1)

    def test_user_edits_during_failed_reanalysis_preserve_the_previous_ai_result(self):
        import json,time,threading
        from unittest.mock import patch
        from PIL import Image
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        from ai_asset_hub_core.analysis_engine import AnalysisEngine
        from ai_asset_hub_core.analysis_results import AssetAnalysis
        from ai_asset_hub_core.annotations import AnnotationService
        Image.new('RGB',(16,16),'red').save(self.source/'나무.png')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0];AssetService(self.db).scan({'library_id':library})
        caps=json.loads(self.db.connection.execute('SELECT capabilities_json FROM model_registry WHERE id=?',(self.model,)).fetchone()[0]);caps['metadataVersion']='a'*64
        self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps(caps),self.model))
        annotations=AnnotationService(self.db);annotations.tags({'asset_id':self.id,'add':['shared','user-only'],'remove':[]})
        jobs=AnalysisJobs(self.db);engine=AnalysisEngine(self.db)
        def start():
            plan=self.params();preview=AnalysisPlan(self.db).preview(plan)
            return jobs.start({'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
        def wait(job):
            deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
        with patch('ai_asset_hub_core.providers.inspect_local',return_value={'status':'available','metadataVersion':'a'*64}),patch('ai_asset_hub_core.inference.infer',return_value=({'description':'AI original','tags':['shared','ai-only']},{'providerRequestAttempted':True})):
            job=start();engine.launch(job);wait(job)
        old=AssetAnalysis(self.db).get({'asset_id':self.id})['active']
        entered=threading.Event();release=threading.Event()
        def failing(*args):entered.set();release.wait(3);raise LibraryError('API_TIMEOUT')
        with patch('ai_asset_hub_core.providers.inspect_local',return_value={'status':'available','metadataVersion':'a'*64}),patch('ai_asset_hub_core.inference.infer',side_effect=failing):
            job=start();engine.launch(job);self.assertTrue(entered.wait(3))
            annotations.save({'asset_id':self.id,'title':'User renamed','description':'Edited while running'})
            annotations.tags({'asset_id':self.id,'add':['edited'],'remove':['shared']})
            release.set();wait(job);engine.close()
        self.assertEqual(AssetAnalysis(self.db).get({'asset_id':self.id})['active']['id'],old['id'])
        self.assertEqual(annotations.get({'asset_id':self.id})['description'],'Edited while running')
        self.assertEqual(set(annotations.get({'asset_id':self.id})['tags']),{'user-only','edited'})
        self.assertEqual(AssetService(self.db).list({})['items'][0]['name'],'User renamed')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_results').fetchone()[0],1)

    def test_audio_and_3d_are_explicit_failures_and_never_sent_to_the_model(self):
        import json,time
        from unittest.mock import patch
        from PIL import Image
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        from ai_asset_hub_core.analysis_engine import AnalysisEngine
        Image.new('RGB',(16,16),'red').save(self.source/'나무.png')
        (self.source/'sound.wav').write_bytes(b'fixture audio');(self.source/'mesh.fbx').write_bytes(b'fixture mesh')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0];AssetService(self.db).scan({'library_id':library})
        caps=json.loads(self.db.connection.execute('SELECT capabilities_json FROM model_registry WHERE id=?',(self.model,)).fetchone()[0]);caps['metadataVersion']='a'*64
        self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps(caps),self.model))
        plan=self.params();preview=AnalysisPlan(self.db).preview(plan)
        self.assertEqual((preview['targetCount'],preview['eligibleCount'],preview['unsupportedCount']),(3,1,2));self.assertEqual(preview['formats']['audio'],1);self.assertEqual(preview['formats']['threeD'],1)
        jobs=AnalysisJobs(self.db);job=jobs.start({'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
        engine=AnalysisEngine(self.db)
        with patch('ai_asset_hub_core.providers.inspect_local',return_value={'status':'available','metadataVersion':'a'*64}) as metadata,patch('ai_asset_hub_core.inference.infer',return_value=({'description':'Fixture image','tags':[]},{'providerRequestAttempted':True})) as inference:
            engine.launch(job);deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
            engine.close();self.assertEqual(inference.call_count,1);self.assertEqual(metadata.call_count,1)
        status=jobs.status({'job_id':job});self.assertEqual((status['succeeded'],status['failed']),(1,2));self.assertTrue(all(e['code']=='UNSUPPORTED_FORMAT' for e in status['errors']))
        self.assertEqual((self.source/'mesh.fbx').read_bytes(),b'fixture mesh')

    def test_no_image_candidates_or_oversize_inputs_cannot_create_jobs(self):
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        (self.source/'audio.wav').write_bytes(b'fixture')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0];AssetService(self.db).scan({'library_id':library})
        audio=self.db.connection.execute("SELECT id FROM assets WHERE display_name='audio.wav'").fetchone()[0]
        for identifier in (audio,self.id):
            if identifier==self.id:
                with open(self.source/'나무.png','wb') as source:source.truncate(20_000_001)
            plan=self.params(mode='selected',selected_ids=[identifier]);preview=AnalysisPlan(self.db).preview(plan)
            self.assertEqual(preview['eligibleCount'],0)
            with self.assertRaises(LibraryError):AnalysisJobs(self.db).start({'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_transparent_pixels_are_composited_and_permission_errors_are_redacted(self):
        import base64,io
        from PIL import Image
        from unittest.mock import patch
        from ai_asset_hub_core.analysis_input import source_info,prepare_image
        Image.new('RGBA',(16,16),(255,0,0,0)).save(self.source/'나무.png');before=(self.source/'나무.png').read_bytes()
        path,info=source_info(self.db,self.id);prepared=prepare_image(self.db,self.id,{'size':info.st_size,'mtimeNs':info.st_mtime_ns})
        with Image.open(io.BytesIO(base64.b64decode(prepared['image']))) as derived:self.assertTrue(all(c>240 for c in derived.getpixel((0,0))))
        self.assertEqual((self.source/'나무.png').read_bytes(),before)
        with patch('ai_asset_hub_core.analysis_input.Path.stat',side_effect=PermissionError('fixture private path')):
            with self.assertRaisesRegex(LibraryError,'FILE_PERMISSION_DENIED'):source_info(self.db,self.id)

    def test_external_adapter_records_reported_usage_without_echoing_credentials(self):
        import json,threading
        from unittest.mock import patch
        from ai_asset_hub_core.inference import infer
        class Socket:
            def settimeout(self,value):pass
        class Response:
            status=200
            leak=False
            def read(self,limit):return json.dumps({'model':'fixture/actual','choices':[{'message':{'content':json.dumps({'description':'fixture-private-key' if self.leak else 'fixture','tags':[]})}}],'usage':{'prompt_tokens':10,'completion_tokens':5,'cost':'0.000002'}}).encode()
        class Connection:
            sock=Socket()
            def __init__(self,*args,**kwargs):pass
            def connect(self):pass
            def request(self,method,path,body,headers):
                self.path=path
                if headers['Authorization']!='Bearer fixture-private-key':raise AssertionError()
            def getresponse(self):return Response()
            def close(self):pass
        with patch('ai_asset_hub_core.inference.http.client.HTTPSConnection',Connection):
            output,usage=infer({'kind':'external','provider':'OpenRouter','modelId':'fixture/requested'}, {'image':'fixture-encoded'},threading.Event(),lambda _:None,'fixture-private-key')
        self.assertEqual(usage['providerReportedCostUsd'],'0.000002');self.assertEqual(usage['responseModel'],'fixture/actual')
        self.assertNotIn('fixture-private-key',json.dumps((output,usage)))
        Response.leak=True
        with patch('ai_asset_hub_core.inference.http.client.HTTPSConnection',Connection):
            with self.assertRaisesRegex(LibraryError,'INVALID_MODEL_OUTPUT'):
                infer({'kind':'external','provider':'OpenRouter','modelId':'fixture/requested'},{'image':'fixture-encoded'},threading.Event(),lambda _:None,'fixture-private-key')

    def test_cancel_between_connect_and_send_cannot_reopen_a_connection(self):
        import threading,http.client
        from unittest.mock import patch
        from ai_asset_hub_core.inference import infer
        canceled=threading.Event();sent=[]
        class Socket:
            def __init__(self,connection):self.connection=connection
            def settimeout(self,value):canceled.set();self.connection.sock=None
        class Connection:
            auto_open=1
            def __init__(self,*args,**kwargs):self.sock=Socket(self)
            def connect(self):pass
            def request(self,*args):
                if self.sock is None and not self.auto_open:raise http.client.NotConnected()
                sent.append(1)
            def close(self):pass
        with patch('ai_asset_hub_core.inference.http.client.HTTPConnection',Connection):
            with self.assertRaisesRegex(LibraryError,'USER_CANCELED'):
                infer({'kind':'local','provider':'Ollama','modelId':'fixture','inspection':{}},{'image':'fixture'},canceled,lambda _:None)
        self.assertEqual(sent,[])

    def test_runtime_connection_failure_is_not_reported_as_a_file_error(self):
        import json,time
        from unittest.mock import patch
        from PIL import Image
        from ai_asset_hub_core.analysis_jobs import AnalysisJobs
        from ai_asset_hub_core.analysis_engine import AnalysisEngine
        Image.new('RGB',(16,16),'red').save(self.source/'나무.png')
        library=self.db.connection.execute('SELECT library_root_id FROM assets').fetchone()[0];AssetService(self.db).scan({'library_id':library})
        caps=json.loads(self.db.connection.execute('SELECT capabilities_json FROM model_registry WHERE id=?',(self.model,)).fetchone()[0]);caps['metadataVersion']='a'*64
        self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps(caps),self.model))
        plan=self.params();preview=AnalysisPlan(self.db).preview(plan);jobs=AnalysisJobs(self.db)
        job=jobs.start({'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
        engine=AnalysisEngine(self.db)
        with patch('ai_asset_hub_core.providers.inspect_local',side_effect=OSError('fixture private address')),patch('ai_asset_hub_core.inference.infer') as inference:
            engine.launch(job);deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
            engine.close();inference.assert_not_called()
        self.assertEqual(jobs.status({'job_id':job})['errors'][0]['code'],'MODEL_UNAVAILABLE')

    def test_local_reasoning_token_limit_cannot_be_saved_as_a_final_result(self):
        import json,threading
        from unittest.mock import MagicMock,patch
        from ai_asset_hub_core.inference import infer
        connection=MagicMock();response=connection.getresponse.return_value;response.status=200
        response.read.return_value=json.dumps({'model':'fixture','done_reason':'length','message':{'content':'','thinking':'private fixture reasoning'}}).encode()
        snapshot={'kind':'local','provider':'Ollama','modelId':'fixture','inspection':{'supportsThinking':True}}
        limits=AnalysisPlan(self.db).preview(self.params(),internal=True)['snapshot']['analysisLimits']
        self.assertEqual(limits['outputTokens'],1024);self.assertEqual(limits['promptSchema'],'asset-description.v3')
        with patch('ai_asset_hub_core.inference.http.client.HTTPConnection',return_value=connection):
            with self.assertRaisesRegex(LibraryError,'MODEL_OUTPUT_LIMIT'):infer(snapshot,{'image':'fixture'},threading.Event(),lambda _:None)
        payload=json.loads(connection.request.call_args.args[2]);self.assertFalse(payload['think'])
        self.assertEqual(payload['options']['num_predict'],1024)
        self.assertEqual(payload['format']['properties']['tags']['maxItems'],8)
        connection.close.assert_called_once()
