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
