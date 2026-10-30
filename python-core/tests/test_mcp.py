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
        group,package,creator=self.add_metadata(identifier)
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
                invalid=await client.call_tool('search_assets',{'query':'나무','limit':True});self.assertTrue(invalid.is_error)
                detail=await client.call_tool('get_asset',{'asset_id':identifier});self.assertFalse(detail.is_error)
                self.assertIsNone(detail.structured_content['activeResult'])
                files=await client.call_tool('get_asset_files',{'asset_id':identifier});self.assertEqual(files.structured_content['files'][0]['availability'],'present')
                status=await client.call_tool('get_analysis_status',{'asset_ids':[identifier]});self.assertFalse(status.structured_content['items'][0]['hasActiveResult'])
                for tool,args in (('list_libraries',{}),('search_assets',{'query':'나무'}),('get_asset',{'asset_id':identifier}),('get_asset_files',{'asset_id':identifier}),('get_analysis_status',{'asset_ids':[identifier]})):
                    legacy=await client.call_tool(tool,args)
                    explicit=await client.call_tool(tool,{**args,'schema_version':1})
                    self.assertEqual(legacy.structured_content,explicit.structured_content)
                    modern=await client.call_tool(tool,{**args,'schema_version':2})
                    self.assertFalse(modern.is_error,modern.content);self.assertEqual(modern.structured_content['schemaVersion'],2)
                    if tool=='get_asset_files':
                        self.assertEqual(modern.structured_content['files'][0]['roles'],['source'])
                        self.assertIsNone(modern.structured_content['files'][0]['technical']['observation'])
                        page=await client.call_tool(tool,{**args,'schema_version':2,'after_component_id':identifier})
                        self.assertFalse(page.is_error,page.content)
                    invalid=await client.call_tool(tool,{**args,'schema_version':True});self.assertTrue(invalid.is_error)
                modern=await client.call_tool('search_assets',{'query':'공개제작사','schema_version':2,'filters':{'types':['A01'],'group_ids':[group],'package_ids':[package],'creator_ids':[creator],'creator_roles':['producer']}})
                self.assertFalse(modern.is_error,modern.content);self.assertEqual(modern.structured_content['items'][0]['id'],identifier)
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

    def add_metadata(self,identifier):
        from ai_asset_hub_core.catalog import Catalog
        from ai_asset_hub_core.packages import Packages
        from ai_asset_hub_core.creators import Creators
        from ai_asset_hub_core.provenance import Provenance
        from ai_asset_hub_core.metadata_store import MetadataStore
        service=Catalog(self.db)
        group=service.group_create({'value':{'name':'공개그룹','description':'PRIVATE-GROUP'}})['id']
        service.group_assign(dict(asset_id=identifier,group_ids=[group],expected_revision=0))
        package=Packages(self.db).package_create({'value':dict(name='공개패키지',description='PRIVATE-PACKAGE',unit='purchase',version='',purchase=dict(amount='123.45',currency='USD',date='2026-10-30'))})['id']
        Packages(self.db).package_assign(dict(asset_id=identifier,package_ids=[package],expected_revision=0))
        creator=Creators(self.db).create({'value':dict(name='공개제작사',kind='company',brand='',homepageUrl='https://example.com/PRIVATE-URL',profileUrl='',contact='PRIVATE-CONTACT',country='',description='PRIVATE-CREATOR')})['id']
        Provenance(self.db).save_links(dict(subject={'kind':'package','id':package},links=[dict(creator_id=creator,role='producer')],expected_revision=0))
        MetadataStore(self.db).classify(identifier,primary='A01.01',facets={'style':['style.pixel']},expected_revision=0,confirmed=True)
        return group,package,creator

    def test_v2_public_projection_combined_filters_and_legacy_contract(self):
        from uuid import uuid4
        _,identifier=self.add_asset();self.add_asset('other.txt');group,package,creator=self.add_metadata(identifier)
        filters={'types':['A01'],'group_ids':[group],'package_ids':[package],'creator_ids':[creator],'creator_roles':['producer']}
        with patch('ai_asset_hub_core.inference.infer',side_effect=AssertionError('no inference')),patch('ai_asset_hub_core.embeddings.embed',side_effect=AssertionError('no embedding')):
            result=self.client.call('search_assets',{'query':'공개제작사','schema_version':2,'filters':filters})
            self.assertEqual([r['id'] for r in result['items']],[identifier])
            metadata=result['items'][0]['metadata']
            self.assertEqual(metadata['groups'][0]['id'],group);self.assertEqual(metadata['packages'][0]['id'],package)
            self.assertEqual(metadata['creators'][0]['id'],creator);self.assertEqual(metadata['creators'][0]['subjectId'],package)
            self.assertEqual(metadata['classification']['value']['primary'],'A01.01')
            detail=self.client.call('get_asset',{'asset_id':identifier,'schema_version':2});self.assertEqual(detail['metadata'],metadata)
            legacy=self.client.call('get_asset',{'asset_id':identifier});self.assertNotIn('metadata',legacy);self.assertNotIn('schemaVersion',legacy)
            for changed in ({'types':['A02']},{'creator_roles':['creator']},{'group_ids':[str(uuid4())]},{'package_ids':[str(uuid4())]},{'creator_ids':[str(uuid4())]},{'include_descendants':False}):
                self.assertEqual(self.client.call('search_assets',{'query':'','schema_version':2,'filters':{**filters,**changed}})['items'],[])
        import json
        raw=json.dumps(detail,ensure_ascii=False)
        for private in ('PRIVATE-','123.45','purchase','contact','homepageUrl'):self.assertNotIn(private,raw)
        for table in ('analysis_jobs','asset_embeddings'):self.assertEqual(self.db.connection.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        self.assertEqual((self.root/'source/숲 나무.png').read_bytes(),b'test-owned')

    def test_versions_and_new_filter_validation_fail_closed_for_all_tools(self):
        _,identifier=self.add_asset()
        for tool,args in (('list_libraries',{}),('search_assets',{'query':''}),('get_asset',{'asset_id':identifier}),('get_asset_files',{'asset_id':identifier}),('get_analysis_status',{'asset_ids':[identifier]})):
            legacy=self.client.call(tool,args)
            self.assertEqual(legacy,self.client.call(tool,{**args,'schema_version':1}))
            modern=self.client.call(tool,{**args,'schema_version':2});self.assertEqual(modern['schemaVersion'],2)
            for version in (True,False,0,3,'2',None,2.0):
                with self.subTest(tool=tool,version=version),self.assertRaisesRegex(BrokerError,'INVALID_PARAMS'):
                    self.client.call(tool,{**args,'schema_version':version})
        for filters in ({'creator_ids':['fake']},{'group_ids':['fake']},{'package_ids':['fake']},{'types':'A01'},{'creator_roles':['owner']},{'include_descendants':1},{'private':True},{'types':['A01']*17}):
            with self.subTest(filters=filters),self.assertRaisesRegex(BrokerError,'INVALID_PARAMS'):
                self.client.call('search_assets',{'query':'','schema_version':2,'filters':filters})
        with self.assertRaisesRegex(BrokerError,'INVALID_PARAMS'):self.client.call('search_assets',{'query':'','filters':{'types':['A01']}})

    def test_v2_filters_apply_before_pagination_and_preserve_unknown_metadata(self):
        _,identifier=self.add_asset();_,second=self.add_asset('second.png');self.add_asset('third.txt')
        for asset in (identifier,second):self.add_metadata(asset)
        request={'query':'','schema_version':2,'filters':{'types':['A01','A02']},'limit':1}
        first=self.client.call('search_assets',request);last=self.client.call('search_assets',{**request,'after_id':first['next_cursor']})
        self.assertEqual({first['items'][0]['id'],last['items'][0]['id']},{identifier,second});self.assertIsNone(last['next_cursor'])
        unknown=self.client.call('search_assets',{'query':'','schema_version':2,'filters':{'types':['__unknown__']}})['items']
        self.assertEqual(len(unknown),1);self.assertIsNone(unknown[0]['metadata']['classification']['value']['primary'])
        self.assertEqual(unknown[0]['metadata']['creators'],[])

    def test_v2_reference_updates_and_queries_do_not_mutate_catalog(self):
        from ai_asset_hub_core.catalog import Catalog
        from ai_asset_hub_core.creators import Creators
        from ai_asset_hub_core.packages import Packages
        from ai_asset_hub_core.mcp_queries import McpQueries
        _,identifier=self.add_asset();group,package,creator=self.add_metadata(identifier)
        service=Catalog(self.db);parent=service.group_create({'value':{'name':'상위그룹','description':''}})['id']
        service.group_move(dict(group_id=group,parent_id=parent,expected_revision=1))
        request={'query':'','schema_version':2,'filters':{'group_ids':[parent]}}
        self.assertEqual(self.client.call('search_assets',request)['items'][0]['id'],identifier)
        self.assertEqual(self.client.call('search_assets',{**request,'filters':{'group_ids':[parent],'include_descendants':False}})['items'],[])
        Creators(self.db).set_enabled(dict(creator_id=creator,enabled=False,expected_revision=1))
        detail=self.client.call('get_asset',{'asset_id':identifier,'schema_version':2})
        self.assertFalse(detail['metadata']['creators'][0]['enabled'])
        self.assertEqual(detail['metadata']['groups'][0]['parentId'],parent)
        Packages(self.db).package_delete(dict(package_id=package,expected_revision=1))
        before='\n'.join(self.db.connection.iterdump());count=self.db.connection.total_changes
        detail=McpQueries(self.db).dispatch('get_asset',{'asset_id':identifier,'schema_version':2})
        self.assertEqual(detail['metadata']['packages'],[]);self.assertEqual(detail['metadata']['creators'],[])
        self.assertEqual('\n'.join(self.db.connection.iterdump()),before);self.assertEqual(self.db.connection.total_changes,count)

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

    def test_audit_records_ids_and_outcomes_without_queries_paths_or_secrets(self):
        from ai_asset_hub_core.mcp_audit import read
        _,identifier=self.add_asset();secret_query='fixture-private-query';secret_host='fixture-private-host-secret'
        self.client.call('get_asset',{'asset_id':identifier},secret_host)
        self.client.call('search_assets',{'query':secret_query},secret_host)
        with self.assertRaisesRegex(BrokerError,'INVALID_PARAMS'):self.client.call('get_asset_files',{'asset_id':'../private-path'},secret_host)
        rows=read(self.db,{})['items'];self.assertEqual(rows[0]['errorCode'],'INVALID_PARAMS');self.assertEqual(rows[0]['outcome'],'denied')
        self.assertTrue(any(identifier in r['targetIds'] for r in rows));self.assertTrue(all(r['requestId'] for r in rows))
        raw=str(self.db.connection.execute('SELECT actor,action,details_redacted_json FROM audit_events').fetchall())
        for secret in (secret_query,secret_host,'../private-path',self.broker.session['token'],str(self.root)):
            self.assertNotIn(secret,raw)

    def test_desktop_audit_paging_and_connection_information_are_allowlisted(self):
        from ai_asset_hub_core.application import CoreApplication
        from uuid import uuid4
        for _ in range(12):self.client.call('list_libraries',{})
        app=CoreApplication(self.db);app._broker=self.broker
        first=app.handle({'request_id':str(uuid4()),'method':'mcp.audit','params':{}})['data'];self.assertEqual(len(first['items']),10)
        second=app.handle({'request_id':str(uuid4()),'method':'mcp.audit','params':{'after_id':first['next_cursor']}})['data']
        self.assertEqual(len(second['items']),2);self.assertIsNone(second['next_cursor'])
        info=app.handle({'request_id':str(uuid4()),'method':'mcp.connection','params':{}})['data'];self.assertTrue(info['brokerReady'])
        self.assertIn('--mcp',info['configuration']['args']);self.assertNotIn(self.broker.session['token'],str(info))
        with self.assertRaisesRegex(BrokerError,'MCP_TOOL_NOT_ALLOWED'):self.client.call('mcp.audit',{})

    def test_tampered_outside_path_is_hidden_and_never_read(self):
        _,identifier=self.add_asset();outside=self.root/'outside-private.txt';outside.write_text('private outside content')
        self.db.connection.execute('UPDATE asset_files SET absolute_path=? WHERE asset_id=?',(str(outside),identifier))
        files=self.client.call('get_asset_files',{'asset_id':identifier})['files']
        self.assertEqual(files[0]['availability'],'unavailable');self.assertNotIn('path',files[0]);self.assertIsNone(files[0]['relativePath'])
        detail=self.client.call('get_asset',{'asset_id':identifier});self.assertFalse(detail['pathValidated']);self.assertIsNone(detail['relativePath'])
        self.assertEqual(outside.read_text(),'private outside content')

    def test_real_windows_junction_cannot_escape_registered_root(self):
        if os.name!='nt':self.skipTest('Windows junction verification')
        import subprocess
        from ai_asset_hub_core.assets import AssetService
        library,_=self.add_asset();nested=self.root/'source/nested';nested.mkdir();(nested/'asset.png').write_bytes(b'fixture')
        AssetService(self.db).scan({'library_id':library})
        identifier=self.db.connection.execute('SELECT asset_id FROM asset_files WHERE absolute_path=?',(str(nested/'asset.png'),)).fetchone()[0]
        (nested/'asset.png').unlink();nested.rmdir();outside=self.root/'outside';outside.mkdir();(outside/'asset.png').write_bytes(b'outside fixture')
        assert nested.resolve().is_relative_to(self.root.resolve()) and outside.resolve().is_relative_to(self.root.resolve())
        result=subprocess.run(['cmd','/c','mklink','/J',str(nested),str(outside)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0)
        try:
            for version in (1,2):
                files=self.client.call('get_asset_files',{'asset_id':identifier,'schema_version':version})['files']
                self.assertEqual(files[0]['availability'],'unavailable');self.assertNotIn('path',files[0]);self.assertIsNone(files[0]['relativePath'])
        finally:nested.rmdir()
        self.assertEqual((outside/'asset.png').read_bytes(),b'outside fixture')
