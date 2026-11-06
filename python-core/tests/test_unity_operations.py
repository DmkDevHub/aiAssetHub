import json
import unittest
from uuid import uuid4
from unittest.mock import patch
import test_unity_connector
from ai_asset_hub_core.unity_targets import UnityTargets
from ai_asset_hub_core.unity_operations import UnityOperations
from ai_asset_hub_core.libraries import LibraryError


class UnityOperationsTests(unittest.TestCase):
    setUp=test_unity_connector.UnityConnectorTests.setUp
    tearDown=test_unity_connector.UnityConnectorTests.tearDown
    connector=test_unity_connector.UnityConnectorTests.connector

    def ready(self):
        from PIL import Image
        Image.new('RGBA',(2,2),(1,2,3,255)).save(self.source/'나무.png')
        project,directory,state,_=self.connector()
        target=UnityTargets(self.db).save(dict(project_path=str(project),confirmed=True))['id']
        return project,directory,state,target,UnityOperations(self.db)

    def test_png_preview_has_real_ids_hash_and_no_project_writes_or_ai(self):
        project,_,_,target,service=self.ready();raw=(self.source/'나무.png').read_bytes()
        result=service.preview_import(dict(target_id=target,asset_ids=[self.id]))
        file=result['items'][0]
        self.assertEqual(file['assetId'],self.id);self.assertEqual(len(file['sha256']),64);self.assertTrue(file['targetRelativePath'].endswith(file['fileId']+'.png'))
        self.assertTrue(result['planOnly']);self.assertNotIn('sourcePath',json.dumps(result));self.assertNotIn('token',json.dumps(result))
        self.assertFalse((project/'Assets/AIAssetHub').exists());self.assertEqual((self.source/'나무.png').read_bytes(),raw)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM unity_operations').fetchone()[0],0)

    def test_preview_rejects_unknown_assets_conflicts_non_png_and_oversize(self):
        project,_,_,target,service=self.ready();request=dict(target_id=target,asset_ids=[self.id])
        with self.assertRaises(LibraryError):service.preview_import(dict(target_id=target,asset_ids=[str(uuid4())]))
        first=service.preview_import(request);destination=project/first['items'][0]['targetRelativePath'];destination.parent.mkdir();destination.write_bytes(b'keep')
        with self.assertRaisesRegex(LibraryError,'UNITY_TARGET_CONFLICT'):service.preview_import(request)
        destination.unlink();(self.source/'나무.png').write_bytes(b'not png')
        with self.assertRaisesRegex(LibraryError,'UNITY_SOURCE_INVALID'):service.preview_import(request)
        with patch('ai_asset_hub_core.unity_operations.MAX_BYTES',1):
            with self.assertRaisesRegex(LibraryError,'UNITY_SOURCE_INVALID'):service.preview_import(request)

    def test_execution_requires_approval_rechecks_source_and_deduplicates_requests(self):
        from ai_asset_hub_core.unity_connector import write_private
        project,directory,state,target,service=self.ready()
        plan=service.preview_import(dict(target_id=target,asset_ids=[self.id]))
        params=dict(plan_id=plan['planId'],request_id=str(uuid4()),confirmed=True,rights_confirmed=True,compatibility_confirmed=True)
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):service.execute_import({**params,'confirmed':False})
        original=(self.source/'나무.png').read_bytes();(self.source/'나무.png').write_bytes(original+b'change')
        with self.assertRaisesRegex(LibraryError,'UNITY_SOURCE_CHANGED'):service.execute_import(params)
        plan=service.preview_import(dict(target_id=target,asset_ids=[self.id]));params['plan_id']=plan['planId']
        queued=service.execute_import(params);self.assertEqual(queued['status'],'queued')
        self.assertEqual(service.execute_import(params)['operationId'],queued['operationId'])
        with self.assertRaisesRegex(LibraryError,'UNITY_PLAN_EXPIRED'):service.execute_import({**params,'request_id':str(uuid4())})
        expected=plan['items'][0]
        write_private(directory/(queued['operationId']+'.result.json'),dict(id=queued['operationId'],session=state['session'],token=state['token'],status='succeeded',
            items=[dict(assetId=self.id,fileId=expected['fileId'],status='succeeded',assetPath=expected['targetRelativePath'],guid='a'*32,copied=True)]))
        result=service.status(dict(operation_id=queued['operationId']))
        self.assertEqual(result['status'],'succeeded');self.assertNotIn('token',json.dumps(result));self.assertNotIn('sourcePath',json.dumps(result))
        (directory/'connector.json').unlink()
        self.assertEqual(service.status(dict(operation_id=queued['operationId'])),result)

    def test_expired_plan_and_fabricated_editor_result_are_rejected(self):
        project,directory,state,target,service=self.ready();plan=service.preview_import(dict(target_id=target,asset_ids=[self.id]))
        with self.assertRaisesRegex(LibraryError,'UNITY_INVALID_RESULT'):service._validate_result(service._plan(plan['planId']),dict(status='succeeded',items=[]))
        with patch('ai_asset_hub_core.unity_operations.time.time',return_value=plan['expiresAt']+1):
            with self.assertRaisesRegex(LibraryError,'UNITY_PLAN_EXPIRED'):service._plan(plan['planId'])

    def test_placement_requires_actual_import_and_unchanged_scene(self):
        from ai_asset_hub_core.unity_connector import write_private
        project,directory,state,target,service=self.ready();plan=service.preview_import(dict(target_id=target,asset_ids=[self.id]))
        params=dict(plan_id=plan['planId'],request_id=str(uuid4()),confirmed=True,rights_confirmed=True,compatibility_confirmed=True)
        queued=service.execute_import(params);item=plan['items'][0];destination=project/item['targetRelativePath'];destination.parent.mkdir();destination.write_bytes((self.source/'나무.png').read_bytes())
        write_private(directory/(queued['operationId']+'.result.json'),dict(id=queued['operationId'],session=state['session'],token=state['token'],status='succeeded',
            items=[dict(assetId=self.id,fileId=item['fileId'],status='succeeded',assetPath=item['targetRelativePath'],guid='a'*32,copied=True)]))
        request=dict(target_id=target,import_operation_id=queued['operationId'],position=[2,3,0],rotation=[0,0,0],scale=[1,1,1],name='Sprite')
        for key,value in (('position',[float('nan'),0,0]),('scale',[0,1,1]),('name','')):
            with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):service.preview_place({**request,key:value})
        place=service.preview_place(request)
        (directory/'connector.json').unlink();state['sceneRevision']+=1;write_private(directory/'connector.json',state)
        with self.assertRaisesRegex(LibraryError,'UNITY_SCENE_CHANGED'):service.execute_place({**params,'plan_id':place['planId'],'request_id':str(uuid4())})
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM unity_operations').fetchone()[0],1)

    def test_cancellation_is_a_request_until_editor_ack_and_survives_reopen(self):
        from ai_asset_hub_core.unity_connector import write_private
        from ai_asset_hub_core.database import Database
        project,directory,state,target,service=self.ready();plan=service.preview_import(dict(target_id=target,asset_ids=[self.id]))
        queued=service.execute_import(dict(plan_id=plan['planId'],request_id=str(uuid4()),confirmed=True,rights_confirmed=True,compatibility_confirmed=True))
        operation=queued['operationId']
        with self.assertRaisesRegex(LibraryError,'INVALID_PARAMS'):service.cancel(dict(operation_id=operation,confirmed=False))
        cancelled=service.cancel(dict(operation_id=operation,confirmed=True));self.assertEqual(cancelled['status'],'queued');self.assertTrue(cancelled['cancelRequested'])
        self.assertEqual(service.cancel(dict(operation_id=operation,confirmed=True)),cancelled)
        request=json.loads((directory/(operation+'.cancel.json')).read_text());self.assertEqual(request['session'],state['session'])
        item=plan['items'][0]
        write_private(directory/(operation+'.result.json'),dict(id=operation,session=state['session'],token=state['token'],status='cancelled',
            items=[dict(assetId=self.id,fileId=item['fileId'],status='cancelled',copied=False,errorCode='UNITY_CANCELLED')]))
        result=service.status(dict(operation_id=operation));self.assertEqual(result['status'],'cancelled');self.assertFalse(result['result']['items'][0]['copied'])
        self.db.close();self.db=Database(self.base/'db.sqlite');service=UnityOperations(self.db)
        self.assertEqual(service.status(dict(operation_id=operation)),result);self.assertEqual(service.list({})['items'][0]['operationId'],operation)
        self.assertFalse((project/item['targetRelativePath']).exists())

    def test_mixed_results_retain_fixed_item_errors_and_unknown_never_becomes_success(self):
        project,directory,state,target,service=self.ready();plan=service.preview_import(dict(target_id=target,asset_ids=[self.id]));internal=service._plan(plan['planId'])
        item=internal['items'][0]
        result=service._validate_result(internal,dict(status='failed',items=[dict(assetId=self.id,fileId=item['fileId'],status='failed',errorCode='PRIVATE-PATH')]))
        self.assertEqual(result['items'][0]['errorCode'],'UNITY_ITEM_FAILED');self.assertNotIn('PRIVATE',json.dumps(result))
        queued=service.execute_import(dict(plan_id=plan['planId'],request_id=str(uuid4()),confirmed=True,rights_confirmed=True,compatibility_confirmed=True))
        with patch('ai_asset_hub_core.unity_operations.time.time',return_value=plan['expiresAt']+100):
            status=service.status(dict(operation_id=queued['operationId']))
        self.assertEqual(status['status'],'unknown');self.assertTrue(status['mayHaveSideEffects']);self.assertIsNone(status['result'])
