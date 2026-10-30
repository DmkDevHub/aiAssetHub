import json
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_analysis
import test_technical
from test_geometry import OBJ
from ai_asset_hub_core.analysis_plan import AnalysisPlan
from ai_asset_hub_core.analysis_jobs import AnalysisJobs
from ai_asset_hub_core.analysis_engine import AnalysisEngine
from ai_asset_hub_core.analysis_results import AssetAnalysis
from ai_asset_hub_core.assets import AssetService


class MultiFormatTests(unittest.TestCase):
    setUp=test_analysis.AnalysisTests.setUp
    tearDown=test_analysis.AnalysisTests.tearDown
    register=test_technical.TechnicalTests.register

    def execute(self,asset,kind,output):
        caps=json.loads(self.db.connection.execute('SELECT capabilities_json FROM model_registry WHERE id=?',(self.model,)).fetchone()[0]);caps['metadataVersion']='a'*64
        self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps(caps),self.model))
        plan={'mode':'selected','scope':'all','library_id':None,'folder_parts':[],'selected_ids':[asset],'model_id':self.model,'input_kind':kind}
        preview=AnalysisPlan(self.db).preview(plan)
        self.assertEqual(preview['eligibleCount'],1)
        job=AnalysisJobs(self.db).start({'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
        engine=AnalysisEngine(self.db)
        with patch('ai_asset_hub_core.providers.inspect_local',return_value={'status':'available','metadataVersion':'a'*64}),patch('ai_asset_hub_core.inference.infer',return_value=(output,{'providerRequestAttempted':True})) as infer:
            engine.launch(job);deadline=time.monotonic()+5
            while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
            engine.close()
        return AnalysisJobs(self.db).status({'job_id':job}),AssetAnalysis(self.db).get({'asset_id':asset})['active'],infer

    def test_geometry_worker_only_sends_safe_derived_image_and_preserves_previous_on_invented_material(self):
        asset=self.register('shape.obj',OBJ)
        status,result,infer=self.execute(asset,'threeD',{'description':'fixture triangle','tags':['triangle'],'suggestions':{'primary':'A02'}})
        self.assertEqual(status['succeeded'],1)
        self.assertEqual(result['features']['technical']['vertexCount'],3)
        prepared=infer.call_args.args[1]
        self.assertEqual(prepared['previewKind'],'wireframe');self.assertNotIn('raw',prepared)
        status,retained,_=self.execute(asset,'threeD',{'description':'bad fixture','tags':[],'suggestions':{'material':['metal']}})
        self.assertEqual(status['failed'],1);self.assertEqual(retained['id'],result['id'])

    def test_animation_worker_keeps_actual_loop_setting_separate_from_ai_recommendation(self):
        from test_animation import gif
        asset=self.register('animation.gif',gif())
        status,result,infer=self.execute(asset,'animation',{'description':'fixture changing colors','tags':['animation'],'suggestions':{'action':'color change','loopRecommended':False}})
        self.assertEqual(status['succeeded'],1)
        self.assertEqual(result['features']['technical']['loopCount'],0)
        self.assertFalse(result['features']['suggestions']['loopRecommended'])
        self.assertEqual(infer.call_args.args[1]['previewKind'],'contact-sheet')
