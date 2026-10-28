from pathlib import Path
import tempfile
import unittest
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.models import ModelService
from ai_asset_hub_core.libraries import LibraryError


class ModelTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]/'.artifacts'/'model-tests';root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.path=Path(self.temp.name)/'db.sqlite'
        self.db=Database(self.path);self.service=ModelService(self.db)

    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def profile(self, **updates):
        return dict(provider_name='fixture provider',kind='local',model_id='fixture-model:version',modalities=['image'],**updates)

    def test_profiles_persist_off_and_duplicates_reuse_real_ids(self):
        profile=self.profile();first=self.service.register(profile)
        self.assertTrue(first['created']);self.assertEqual(self.service.register(profile),{'id':first['id'],'created':False})
        self.db.close();self.db=Database(self.path);self.service=ModelService(self.db)
        row=self.service.list({})['items'][0]
        self.assertEqual(row['id'],first['id']);self.assertFalse(row['enabled'])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_invalid_registration_does_not_leave_provider_or_model(self):
        for key,value in [('kind','remote'),('provider_name',''),('model_id','x'*161),('modalities',['bad']),('modalities',[])]:
            profile=self.profile();profile[key]=value
            with self.assertRaises(LibraryError):self.service.register(profile)
        self.assertEqual(self.service.list({})['items'],[])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM model_providers').fetchone()[0],0)

    def test_pagination_returns_each_model_once(self):
        for n in range(12):
            profile=self.profile();profile['model_id']=f'fixture-{n}';self.service.register(profile)
        first=self.service.list({});second=self.service.list({'after_id':first['next_cursor']})
        self.assertEqual((len(first['items']),len(second['items'])),(10,2))
        self.assertIsNone(second['next_cursor'])

    def test_local_inspection_is_explicit_and_persists_actual_capabilities(self):
        from unittest.mock import patch
        profile=self.profile();profile['provider_name']='Ollama';identifier=self.service.register(profile)['id']
        with patch('ai_asset_hub_core.providers.metadata',return_value={'capabilities':['completion','vision']}) as request:
            self.assertFalse(request.called)
            result=self.service.inspect({'id':identifier})
            request.assert_called_once_with('http://127.0.0.1:11434/api/show',{'model':profile['model_id']})
        self.assertEqual(result['status'],'available');self.assertFalse(result['inferenceCalled'])
        self.assertEqual(result['modalities'],['text','image'])
        self.assertTrue(self.service.list({})['items'][0]['inspection']['verified'])
        with patch('ai_asset_hub_core.providers.metadata',side_effect=TimeoutError('private')):
            self.assertEqual(self.service.inspect({'id':identifier})['status'],'unavailable')
        self.assertFalse(self.service.list({})['items'][0]['enabled'])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_metadata_transport_uses_bounded_json_and_blocks_redirects(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from threading import Thread
        from ai_asset_hub_core.providers import metadata
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','https://example.invalid');self.end_headers();return
                self.send_response(200);self.end_headers();self.wfile.write(b'{"fixture":true}')
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}'
            self.assertEqual(metadata(url),{'fixture':True})
            with self.assertRaises(Exception):metadata(url+'/redirect')
        finally:server.shutdown();server.server_close();thread.join()

    def test_external_requires_consent_and_classifies_verified_prices(self):
        from unittest.mock import patch
        profile=self.profile();profile.update(provider_name='OpenRouter',kind='external',model_id='fixture/exact-model')
        identifier=self.service.register(profile)['id']
        with patch('ai_asset_hub_core.providers.metadata') as request:
            self.assertEqual(self.service.inspect({'id':identifier})['status'],'external_consent_required');request.assert_not_called()
        data={'data':[{'id':profile['model_id'],'architecture':{'input_modalities':['image','text']},'pricing':{'prompt':'0','completion':'0'}}]}
        with patch('ai_asset_hub_core.providers.metadata',return_value=data) as request:
            result=self.service.inspect({'id':identifier,'allow_external':True})
            self.assertEqual(result['costClass'],'free');self.assertFalse(result['inferenceCalled'])
            self.assertEqual(result['authentication'],'not_tested')
            request.assert_called_once_with('https://openrouter.ai/api/v1/models',key=None)
        data['data'][0]['pricing']['prompt']='0.001'
        with patch('ai_asset_hub_core.providers.metadata',return_value=data):
            self.assertEqual(self.service.inspect({'id':identifier,'allow_external':True})['costClass'],'paid')
        data['data'][0]['pricing']['prompt']='NaN'
        with patch('ai_asset_hub_core.providers.metadata',return_value=data):
            self.assertEqual(self.service.inspect({'id':identifier,'allow_external':True})['status'],'unavailable')
        self.assertFalse(self.service.list({})['items'][0]['enabled'])

    def test_windows_vault_roundtrip_is_scoped_and_never_stored_in_database(self):
        import os,json
        if os.name!='nt':self.skipTest('Windows vault only')
        profile=self.profile();profile.update(provider_name='OpenRouter',kind='external')
        identifier=self.service.register(profile)['id'];secret='fixture-private-credential-value'
        try:
            self.service.credential({'id':identifier,'action':'save','key':secret})
            self.assertEqual(self.service.vault.read(identifier),secret)
            self.assertTrue(self.service.list({})['items'][0]['hasCredential'])
            self.assertNotIn(secret,json.dumps(self.service.list({})))
            for table,column in [('model_registry','capabilities_json'),('settings','value_json')]:
                self.assertNotIn(secret,str(self.db.connection.execute(f'SELECT {column} FROM {table}').fetchall()))
            from unittest.mock import patch
            with patch('ai_asset_hub_core.providers.metadata',return_value={'data':{}}) as request:
                self.assertEqual(self.service.credential({'id':identifier,'action':'test','allow_external':True})['status'],'authenticated')
                request.assert_called_once_with('https://openrouter.ai/api/v1/key',key=secret)
            self.service.credential({'id':identifier,'action':'delete'})
            self.assertIsNone(self.service.vault.read(identifier))
        finally:self.service.vault.delete(identifier)
