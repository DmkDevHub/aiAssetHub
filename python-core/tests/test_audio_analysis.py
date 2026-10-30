import json
import threading
import time
import unittest
from datetime import datetime,timezone
from unittest.mock import patch,MagicMock
from uuid import uuid4
import test_annotations
import test_technical
from test_technical import wav
from ai_asset_hub_core.analysis_jobs import AnalysisJobs
from ai_asset_hub_core.analysis_plan import AnalysisPlan
from ai_asset_hub_core.analysis_engine import AnalysisEngine
from ai_asset_hub_core.analysis_results import AssetAnalysis
from ai_asset_hub_core.libraries import LibraryError
from ai_asset_hub_core.models import ModelService


class AudioTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown
    register=test_technical.TechnicalTests.register

    def test_external_audio_is_explicit_bounded_and_saves_transcript_as_a_proposal(self):
        asset=self.register('목소리.wav',wav());service=ModelService(self.db)
        model=service.register({'provider_name':'OpenRouter','kind':'external','model_id':'fixture/audio','modalities':['audio']})['id']
        caps={'status':'available','verified':True,'modalities':['audio'],'checkedAt':datetime.now(timezone.utc).isoformat(),'authentication':'authenticated','costClass':'paid','contextLength':4096,'pricing':{'prompt':'0.000001','completion':'0.000002','audio':'0.000003'}}
        self.db.connection.execute('UPDATE model_registry SET capabilities_json=? WHERE id=?',(json.dumps(caps),model))
        plan={'mode':'selected','scope':'all','library_id':None,'folder_parts':[],'selected_ids':[asset],'model_id':model,'input_kind':'audio'}
        with patch('ai_asset_hub_core.credentials.Vault.read',return_value='fixture-key'):
            service.policy({'id':model,'enabled':True,'allow_external':True,'allow_paid':True,'budget_usd':'1','max_requests':10})
            preview=AnalysisPlan(self.db).preview(plan)
            self.assertEqual(preview['eligibleCount'],1);self.assertTrue(preview['externalTransfer'])
            self.assertEqual(preview['estimatedUpperBoundUsd'],'0.013312')
            request={'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':True}
            with self.assertRaisesRegex(LibraryError,'MODEL_POLICY_DENIED'):AnalysisJobs(self.db).start(request)
            request['confirm_external']=True
            job=AnalysisJobs(self.db).start(request)['jobId']
            connection=MagicMock();response=connection.getresponse.return_value;response.status=200
            response.read.return_value=json.dumps({'model':'fixture/audio','choices':[{'message':{'content':json.dumps({'description':'fixture voice','tags':['voice'],'audioSuggestions':{'soundClass':'voice','mood':['calm'],'transcript':'fixture transcript'}})}}]}).encode()
            engine=AnalysisEngine(self.db)
            with patch('ai_asset_hub_core.providers.inspect_external',return_value=caps),patch('ai_asset_hub_core.inference.http.client.HTTPSConnection',return_value=connection):
                engine.launch(job);deadline=time.monotonic()+5
                while engine.active(job) and time.monotonic()<deadline:time.sleep(.01)
                engine.close()
            self.assertEqual(AnalysisJobs(self.db).status({'job_id':job})['succeeded'],1)
            payload=json.loads(connection.request.call_args.args[2]);media=payload['messages'][0]['content'][1]
            self.assertEqual(media['type'],'input_audio');self.assertEqual(media['input_audio']['format'],'wav')
            result=AssetAnalysis(self.db).get({'asset_id':asset})['active']['features']
            self.assertEqual(result['technical']['channels'],2)
            self.assertEqual(result['audioSuggestions']['transcript'],'fixture transcript')
            self.assertEqual(result['suggestionStatus'],'proposed')

    def test_audio_validation_rejects_wrong_fields_and_canceled_http_never_sends(self):
        from ai_asset_hub_core.analysis_features import audio_suggestions
        from ai_asset_hub_core.inference import infer
        for value in ({'soundClass':'fake'},{'durationSeconds':1},{'transcript':'x'*2049},{'mood':['\0']}):
            with self.assertRaises(LibraryError):audio_suggestions(value)
        canceled=threading.Event();canceled.set()
        with patch('ai_asset_hub_core.inference.http.client.HTTPSConnection') as connection:
            with self.assertRaisesRegex(LibraryError,'USER_CANCELED'):infer({'kind':'external','provider':'OpenRouter','inputModality':'audio'},{},canceled,lambda _:None,'fixture-key')
            connection.assert_not_called()
