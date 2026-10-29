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
        async def host():
            packages=ROOT/'.artifacts/core-build-venv/Lib/site-packages'
            bootstrap='import site,runpy;site.addsitedir('+repr(str(packages))+');runpy.run_module("ai_asset_hub_core",run_name="__main__")'
            config=StdioServerParameters(command=sys.executable,args=['-B','-c',bootstrap,'--mcp','--data-dir',str(self.root/'data')],cwd=ROOT/'python-core',env=dict(os.environ))
            async with Client(config,read_timeout_seconds=5) as client:
                self.assertEqual(client.server_info.name,'AI Asset Hub')
                self.assertEqual(client.server_info.version,'0.5.0')
                self.assertEqual((await client.list_tools()).tools,[])
                self.assertTrue(client.protocol_version)
        asyncio.run(host())
