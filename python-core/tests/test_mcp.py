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
