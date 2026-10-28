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

    def history(self, identifier, status, active=False, timestamp='2026-10-28T00:00:00Z'):
        job,run,result=[str(uuid4()) for _ in range(3)];db=self.db.connection
        db.execute("INSERT INTO analysis_jobs(id,request_id,scope_json,model_snapshot_json,requested_count,status,created_at,initiated_by) VALUES (?,?,'{}','{}',1,?,?,'fixture')",(job,str(uuid4()),status,timestamp))
        db.execute('INSERT INTO analysis_job_items(job_id,asset_id,status) VALUES (?,?,?)',(job,identifier,status))
        db.execute("INSERT INTO analysis_runs(id,job_id,asset_id,model_snapshot_json,input_fingerprint,status,created_at) VALUES (?,?,?,'{}','fixture',?,?)",(run,job,identifier,status,timestamp))
        if active:
            db.execute("INSERT INTO analysis_results(id,run_id,asset_id,description,tags_json,features_json,created_at) VALUES (?,?,?,'fixture successful','[]','{}',?)",(result,run,identifier,timestamp))
            db.execute('INSERT INTO asset_active_results VALUES (?,?,?)',(identifier,result,timestamp))

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
        with patch('ai_asset_hub_core.providers.inspect_local',return_value={'status':'available','metadataVersion':'a'*64}),patch('ai_asset_hub_core.inference.infer',return_value=({'description':'Fixture red image','tags':['red']},{'providerRequestAttempted':True})):
            engine.launch(job)
            deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
            engine.close()
        self.assertEqual(AnalysisJobs(self.db).status({'job_id':job})['succeeded'],1)
        self.assertEqual(AssetAnalysis(self.db).get({'asset_id':self.id})['active']['description'],'Fixture red image')
        self.assertEqual(AnnotationService(self.db).get({'asset_id':self.id})['tags'],['mine'])
        self.assertFalse(asset_state(self.db.connection,self.id)['analysisStale'])
        self.assertEqual((self.source/'나무.png').read_bytes(),before)
