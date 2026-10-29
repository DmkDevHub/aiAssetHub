import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from ai_asset_hub_core.runtime import CoreRuntime
from ai_asset_hub_core.mcp_broker import Broker,BrokerClient,BrokerError

ROOT=Path(__file__).resolve().parents[2]


class McpTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'.artifacts/mcp-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.temp.name)
        self.runtime=CoreRuntime(self.root/'data','development')
        self.db=self.runtime.database
        self.broker=Broker(self.runtime.database);self.client=BrokerClient(self.root/'data')

    def tearDown(self):
        self.broker.close();self.runtime.close();self.temp.cleanup()

    def test_real_local_broker_and_session_cleanup(self):
        self.assertEqual(self.client.call('_health',{}),{'status':'ready'})
        self.assertEqual(self.runtime.database.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        self.broker.close()
        with self.assertRaisesRegex(BrokerError,'APP_NOT_RUNNING'):self.client.call('_health',{})

    def test_official_sdk_host_initializes_a_real_stdio_bridge_process(self):
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters
        library,identifier=self.add_asset()
        async def host():
            packages=ROOT/'.artifacts/core-build-venv/Lib/site-packages'
            bootstrap='import site,runpy;site.addsitedir('+repr(str(packages))+');runpy.run_module("ai_asset_hub_core",run_name="__main__")'
            config=StdioServerParameters(command=sys.executable,args=['-B','-c',bootstrap,'--mcp','--data-dir',str(self.root/'data')],cwd=ROOT/'python-core',env=dict(os.environ))
            async with Client(config,read_timeout_seconds=5) as client:
                self.assertEqual(client.server_info.name,'AI Asset Hub')
                self.assertEqual(client.server_info.version,'0.5.0')
                self.assertEqual({t.name for t in (await client.list_tools()).tools},{'list_libraries','search_assets','get_asset','get_asset_files','get_analysis_status'})
                self.assertTrue(client.protocol_version)
                libraries=await client.call_tool('list_libraries',{})
                self.assertFalse(libraries.is_error);self.assertEqual(libraries.structured_content['items'][0]['id'],library)
                results=await client.call_tool('search_assets',{'query':'나무'})
                self.assertFalse(results.is_error);self.assertEqual(results.structured_content['items'][0]['id'],identifier)
                detail=await client.call_tool('get_asset',{'asset_id':identifier});self.assertFalse(detail.is_error)
                self.assertIsNone(detail.structured_content['activeResult'])
                files=await client.call_tool('get_asset_files',{'asset_id':identifier});self.assertEqual(files.structured_content['files'][0]['availability'],'present')
                status=await client.call_tool('get_analysis_status',{'asset_ids':[identifier]});self.assertFalse(status.structured_content['items'][0]['hasActiveResult'])
                self.broker.close()
                unavailable=await client.call_tool('list_libraries',{})
                self.assertTrue(unavailable.is_error);self.assertIn('APP_NOT_RUNNING',str(unavailable.content))
        asyncio.run(host())

    def add_asset(self,name='숲 나무.png'):
        from ai_asset_hub_core.libraries import LibraryService
        from ai_asset_hub_core.assets import AssetService
        source=self.root/'source';source.mkdir(exist_ok=True);(source/name).write_bytes(b'test-owned')
        library=LibraryService(self.runtime.database).register({'path':str(source)})['library']['id']
        AssetService(self.runtime.database).scan({'library_id':library})
        identifier=self.runtime.database.connection.execute('SELECT asset_id FROM asset_files WHERE relative_path=?',(name,)).fetchone()[0]
        return library,identifier

    def test_offline_search_returns_actual_ids_filters_and_no_model_jobs(self):
        library,identifier=self.add_asset();self.add_asset('other.txt')
        with patch('ai_asset_hub_core.embeddings.embed',side_effect=AssertionError('no inference')),patch('ai_asset_hub_core.providers.metadata',side_effect=AssertionError('no network')):
            self.assertEqual(self.client.call('list_libraries',{})['items'][0]['id'],library)
            result=self.client.call('search_assets',{'query':'나무','filters':{'library_id':library,'kind':'PNG'},'limit':1})
            self.assertEqual([i['id'] for i in result['items']],[identifier]);self.assertFalse(result['modelCalled'])
            self.assertEqual(self.client.call('search_assets',{'query':'나무','filters':{'kind':'FBX'}})['items'],[])
            with self.assertRaisesRegex(BrokerError,'INVALID_PARAMS'):self.client.call('search_assets',{'query':'나무','mode':'semantic'})
        self.assertEqual(self.runtime.database.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)
        self.assertEqual(self.runtime.database.connection.execute('SELECT count(*) FROM asset_embeddings').fetchone()[0],0)

    def test_search_pagination_is_stable_and_invalid_filters_cannot_escape(self):
        self.add_asset();self.add_asset('second.png')
        first=self.client.call('search_assets',{'query':'','limit':1});second=self.client.call('search_assets',{'query':'','limit':1,'after_id':first['next_cursor']})
        self.assertEqual(len({first['items'][0]['id'],second['items'][0]['id']}),2);self.assertIsNone(second['next_cursor'])
        for params in ({'query':'x','filters':{'folder_parts':['..']}},{'query':'x','limit':True},{'query':'x','after_id':'invented-id'},{'query':'x','limit':21}):
            with self.assertRaisesRegex(BrokerError,'INVALID_PARAMS'):self.client.call('search_assets',params)

    def test_details_keep_active_success_and_latest_failure_distinct_without_preview_writes(self):
        import test_analysis
        _,identifier=self.add_asset()
        test_analysis.AnalysisTests.history(self,identifier,'completed',True)
        test_analysis.AnalysisTests.history(self,identifier,'failed',timestamp='2026-10-28T00:00:01Z')
        with patch('ai_asset_hub_core.thumbnails.thumbnail',side_effect=AssertionError('no thumbnail generation')),patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('no inference')):
            detail=self.client.call('get_asset',{'asset_id':identifier})
            self.assertEqual(detail['activeResult']['description'],'fixture successful')
            self.assertEqual(detail['history']['items'][0]['status'],'failed')
            state=self.client.call('get_analysis_status',{'asset_ids':[identifier]})['items'][0]
            self.assertTrue(state['hasActiveResult']);self.assertEqual(state['lastAttemptState'],'failed')
            files=self.client.call('get_asset_files',{'asset_id':identifier})['files'];self.assertEqual(files[0]['availability'],'present')
            (self.root/'source/숲 나무.png').unlink()
            self.assertEqual(self.client.call('get_asset_files',{'asset_id':identifier})['files'][0]['availability'],'missing')

    def test_unknown_and_disabled_asset_details_are_not_fabricated(self):
        from uuid import uuid4
        from ai_asset_hub_core.libraries import LibraryService
        library,identifier=self.add_asset();LibraryService(self.db).unregister({'library_id':library})
        for tool in ('get_asset','get_asset_files'):
            for value in (identifier,str(uuid4())):
                with self.assertRaisesRegex(BrokerError,'MCP_ASSET_NOT_FOUND'):self.client.call(tool,{'asset_id':value})
            with self.assertRaisesRegex(BrokerError,'INVALID_PARAMS'):self.client.call(tool,{'asset_id':'invented-id'})
        with self.assertRaisesRegex(BrokerError,'MCP_ASSET_NOT_FOUND'):self.client.call('get_analysis_status',{'asset_ids':[identifier]})

    def raw(self,request):
        import socket
        from ai_asset_hub_core.mcp_broker import encode,receive
        with socket.create_connection(('127.0.0.1',self.broker.session['port']),timeout=2) as connection:
            connection.sendall(encode(request));return receive(connection)

    def test_authentication_denies_bad_mac_replay_and_all_write_commands(self):
        from uuid import uuid4
        from ai_asset_hub_core.mcp_broker import signature
        request={'session':self.broker.session['session'],'request_id':str(uuid4()),'host':'reference-host','tool':'_health','arguments':{},'mac':'0'*64}
        self.assertEqual(self.raw(request)['error'],'AUTH_DENIED')
        old=dict(self.broker.session);self.broker.close();self.broker=Broker(self.db)
        request['mac']=signature(request,old['token']);self.assertEqual(self.raw(request)['error'],'AUTH_DENIED')
        self.assertNotEqual(old['token'],self.broker.session['token'])
        for tool in ('analysis.start','embedding.query','library.scan','asset.annotate','import_assets_to_unity'):
            with self.assertRaisesRegex(BrokerError,'MCP_TOOL_NOT_ALLOWED'):self.client.call(tool,{'confirmed':True})
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0],0)

    def test_fake_server_cannot_forge_responses_or_obtain_the_session_secret(self):
        import socket,threading,json
        from ai_asset_hub_core.mcp_broker import receive,encode
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);captured=[]
        def fake():
            with listener:
                connection,_=listener.accept()
                with connection:
                    request=receive(connection);captured.append(json.dumps(request))
                    connection.sendall(encode({'ok':True,'data':{'invented':True},'request_id':request['request_id'],'session':request['session'],'pid':os.getpid(),'mac':'0'*64}))
        thread=threading.Thread(target=fake,daemon=True);thread.start()
        info={**self.broker.session,'port':listener.getsockname()[1]}
        with patch('ai_asset_hub_core.session_file.read',return_value=info):
            with self.assertRaisesRegex(BrokerError,'CORE_UNAVAILABLE'):self.client.call('_health',{})
        thread.join(2);self.assertFalse(thread.is_alive());self.assertNotIn(info['token'],captured[0])

    def test_slow_unterminated_peer_is_bounded_and_does_not_kill_core(self):
        import socket,time
        connection=socket.create_connection(('127.0.0.1',self.broker.session['port']),timeout=2)
        started=time.monotonic()
        try:
            connection.sendall(b'{');time.sleep(1.7)
            self.assertTrue(connection.recv(4096));self.assertLess(time.monotonic()-started,3)
        finally:connection.close()
        self.assertEqual(self.client.call('_health',{})['status'],'ready')

    def test_permissive_windows_discovery_acl_is_rejected(self):
        if os.name!='nt':self.skipTest('Windows DACL verification')
        import ctypes as c
        from ctypes import wintypes as w
        from ai_asset_hub_core.session_file import private
        adv=c.WinDLL('advapi32',use_last_error=True);kernel=c.WinDLL('kernel32',use_last_error=True)
        adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[w.LPCWSTR,w.DWORD,c.POINTER(c.c_void_p),c.POINTER(w.DWORD)]
        adv.SetFileSecurityW.argtypes=[w.LPCWSTR,w.DWORD,c.c_void_p];kernel.LocalFree.argtypes=[c.c_void_p]
        descriptor=c.c_void_p();self.assertTrue(adv.ConvertStringSecurityDescriptorToSecurityDescriptorW('D:P(A;;FA;;;WD)',1,c.byref(descriptor),None))
        try:self.assertTrue(adv.SetFileSecurityW(str(self.broker.discovery),0x80000004,descriptor))
        finally:kernel.LocalFree(descriptor)
        try:
            with self.assertRaisesRegex(BrokerError,'APP_NOT_RUNNING'):self.client.call('_health',{})
        finally:private(self.broker.discovery,True)

    def test_malformed_frames_and_oversized_responses_fail_without_raw_data(self):
        import socket
        from ai_asset_hub_core.mcp_broker import receive,MAX_FRAME
        for raw in (b'{"duplicate":1,"duplicate":2}\n',b'x'*(MAX_FRAME+1)):
            with socket.create_connection(('127.0.0.1',self.broker.session['port']),timeout=2) as connection:
                connection.sendall(raw);result=receive(connection)
                self.assertFalse(result['ok']);self.assertEqual(result['error'],'INVALID_PARAMS')
        with patch.object(self.broker,'dispatch',return_value={'private':'x'*MAX_FRAME}):
            with self.assertRaisesRegex(BrokerError,'MCP_RESPONSE_LIMIT'):self.client.call('_health',{})
        self.assertEqual(self.client.call('_health',{})['status'],'ready')
