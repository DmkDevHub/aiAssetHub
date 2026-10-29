"""Real reference Host -> packaged stdio Bridge -> running packaged Core, no GUI/AI."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import time
from uuid import uuid4
from importlib.util import spec_from_file_location,module_from_spec

ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('local_verification',ROOT/'scripts/verify-local-analysis.py')
helper=module_from_spec(spec);spec.loader.exec_module(helper)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core',required=True);parser.add_argument('--report',required=True);args=parser.parse_args()
    executable=Path(args.core).resolve(strict=True);root=ROOT/'.artifacts'/('mcp-real-'+str(uuid4()));root.mkdir()
    core=helper.InstalledCore(executable,root/'data')
    async def host():
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters
        environment=dict(os.environ);environment['PATH']=str(Path(os.environ['SystemRoot'])/'System32');environment.pop('PYTHONHOME',None);environment.pop('PYTHONPATH',None)
        parameters=StdioServerParameters(command=str(executable),args=['--mcp','--data-dir',str(root/'data')],cwd=executable.parent,env=environment)
        async with Client(parameters,read_timeout_seconds=10) as client:
            tools=await client.list_tools()
            return {'host':'official Python MCP SDK Client','protocolVersion':client.protocol_version,'server':client.server_info.name,'tools':[t.name for t in tools.tools],'guiOpened':False,'pythonOnPath':False}
    try:
        report=asyncio.run(host());report['corePid']=core.child.pid
        Path(args.report).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
    finally:core.close()


if __name__=='__main__':main()
