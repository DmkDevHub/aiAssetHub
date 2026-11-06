import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_annotations
from ai_asset_hub_core.application import CoreApplication
from ai_asset_hub_core.libraries import LibraryError
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.thumbnails import thumbnail
from ai_asset_hub_core.mcp_queries import McpQueries
from ai_asset_hub_core.mcp_audit import record,read


class ReleaseSecurityTests(unittest.TestCase):
    setUp=test_annotations.AnnotationTests.setUp
    tearDown=test_annotations.AnnotationTests.tearDown

    def test_read_scan_diagnostics_and_disabled_external_models_make_zero_network_or_ai_calls(self):
        app=CoreApplication(self.db)
        def call(method,params):return app.handle(dict(request_id=str(uuid4()),method=method,params=params))
        before=(self.source/'나무.png').read_bytes();library=self.db.connection.execute('SELECT id FROM library_roots').fetchone()[0]
        with patch('socket.create_connection',side_effect=AssertionError('network blocked')) as network,patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('inference blocked')) as inference:
            for method,params in (('library.list',{}),('library.scan',dict(library_id=library)),('asset.list',dict(limit=100)),('asset.search',dict(query='나무')),('diagnostics.read',dict(kind='analysis')),('diagnostics.budget',{})):
                self.assertTrue(call(method,params)['ok'],method)
            model=call('model.register',dict(provider_name='OpenRouter',kind='external',model_id='owned-fixture-off',modalities=['image']))['data']['id']
            inspected=call('model.inspect',dict(id=model,allow_external=False));self.assertEqual(inspected['data']['status'],'external_consent_required')
            self.assertFalse(call('model.validate',dict(id=model,modality='image'))['data']['compatible'])
            self.assertFalse(call('analysis.start',dict(confirmed=False))['ok'])
            for tool in ('maintenance.backup','maintenance.restore','diagnostics.read','library.scan.start','analysis.start'):
                with self.assertRaisesRegex(LibraryError,'MCP_TOOL_NOT_ALLOWED'):McpQueries(self.db).dispatch(tool,{})
            network.assert_not_called();inference.assert_not_called()
        self.assertEqual((self.source/'나무.png').read_bytes(),before)
        for table in ('analysis_jobs','asset_embeddings','unity_operations'):self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def junction(self,link,target):
        result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0)

    def test_real_windows_cache_and_replaced_source_root_junction_never_write_outside(self):
        if os.name!='nt':self.skipTest('Windows-only boundary')
        from PIL import Image
        Image.new('RGB',(4,4),'red').save(self.source/'나무.png')
        outside=self.base/'outside';outside.mkdir();(outside/'keep.txt').write_bytes(b'owned outside sentinel')
        cache=self.base/'thumbnails';self.junction(cache,outside)
        try:self.assertEqual(thumbnail(self.db,dict(asset_id=self.id))['status'],'unavailable');self.assertEqual([p.name for p in outside.iterdir()],['keep.txt'])
        finally:cache.rmdir()
        held=self.base/'held';self.source.rename(held);self.junction(self.source,outside)
        try:
            library=self.db.connection.execute('SELECT id FROM library_roots').fetchone()[0]
            with self.assertRaises(LibraryError):AssetService(self.db).scan(dict(library_id=library))
            self.assertEqual(AssetService(self.db).get(dict(asset_id=self.id))['availability'],'unavailable')
            files=McpQueries(self.db).dispatch('get_asset_files',dict(asset_id=self.id,schema_version=2))['files'];self.assertNotIn('path',files[0])
            self.assertEqual((outside/'keep.txt').read_bytes(),b'owned outside sentinel')
        finally:self.source.rmdir();held.rename(self.source)

    def test_private_inputs_and_exception_strings_do_not_reach_errors_or_audit(self):
        app=CoreApplication(self.db);secret='PRIVATE-token/path?key=secret'
        result=app.handle(dict(request_id=str(uuid4()),method=secret,params={'key':secret}));self.assertNotIn(secret,json.dumps(result))
        request=dict(tool='search_assets',host=secret,arguments=dict(query=secret),request_id=str(uuid4()))
        record(self.db,request,dict(ok=False,error='INVALID_PARAMS'),True,time.monotonic())
        audit=read(self.db,{});self.assertNotIn(secret,json.dumps(audit));self.assertEqual(audit['items'][0]['host'],'other-host')
