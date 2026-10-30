"""Real reference Host -> packaged stdio Bridge -> running packaged Core, no GUI/AI."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import time
import hashlib
from uuid import uuid4
from importlib.util import spec_from_file_location,module_from_spec

ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('local_verification',ROOT/'scripts/verify-local-analysis.py')
helper=module_from_spec(spec);spec.loader.exec_module(helper)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core',required=True);parser.add_argument('--report',required=True);parser.add_argument('--data-dir');parser.add_argument('--environment',choices=['development','production'],default='production');parser.add_argument('--query',default='mcp-fixture');parser.add_argument('--require-analyzed',action='store_true');args=parser.parse_args()
    executable=Path(args.core).resolve(strict=True);root=ROOT/'.artifacts'/('mcp-real-'+str(uuid4()));root.mkdir()
    data=Path(args.data_dir).resolve() if args.data_dir else root/'data'
    if not data.is_relative_to((ROOT/'.artifacts').resolve()):raise RuntimeError('TEST_DATA_MUST_BE_OWNED_ARTIFACT')
    core=helper.InstalledCore(executable,data,args.environment);initial_pid=core.child.pid
    if not args.data_dir:
        from PIL import Image
        source=root/'source';source.mkdir();Image.new('RGB',(16,16),'green').save(source/'mcp-fixture.png')
        library=core.call('library.register',{'path':str(source)})['library']['id'];core.call('library.scan',{'library_id':library})
        fixture_id=core.call('asset.list')['items'][0]['id'];subject={'kind':'asset','id':fixture_id}
        creator=core.call('creator.create',{'value':{'name':'fixture creator','kind':'person','brand':'','homepageUrl':'','profileUrl':'','contact':'PRIVATE-PROVENANCE-CONTACT','country':'','description':''}})
        core.call('creator.links.save',{'subject':subject,'links':[{'creator_id':creator['id'],'role':'creator'}],'expected_revision':0})
        provenance_source=core.call('source.create',{'subject':subject,'value':{'site':'fixture','productName':'fixture product','originalUrl':'','productUrl':'','downloadUrl':'https://example.com/?key=PRIVATE-PROVENANCE-URL','purchase':{'amount':'12345.6789','currency':'KRW','purchasedOn':'2024-02-29','downloadedOn':''}}})
        license=core.call('license.create',{'subject':subject,'confirmed':True,'value':{'label':'declared fixture license','terms':'PRIVATE-PROVENANCE-TERMS','attribution':'fixture credit','reviewStatus':'unknown','scope':'fixture','note':'PRIVATE-PROVENANCE-NOTE','source_id':provenance_source['id']}})
        file_id=core.call('asset.composition',{'asset_id':fixture_id})['value']['files'][0]['fileId']
        core.call('license.evidence.save',{'record_id':license['id'],'files':[{'file_id':file_id,'label':'PRIVATE-PROVENANCE-PROOF'}],'expected_revision':1,'confirmed':True})
        for kind in ('creators','sources','licenses'):
            exported=core.call('provenance.export',{'subject':subject,'kind':kind,'after_id':None})
            assert 'PRIVATE-PROVENANCE' not in json.dumps(exported) and '12345.6789' not in json.dumps(exported)

    before_jobs=core.call('analysis.jobs');before_embeddings=core.call('embedding.status')
    hashes={};cursor=None
    while True:
        page=core.call('asset.list',{'after_id':cursor})
        for asset in page['items']:
            path=Path(asset['path']).resolve()
            if not path.is_relative_to((ROOT/'.artifacts').resolve()):raise RuntimeError('TEST_SOURCE_MUST_BE_OWNED_ARTIFACT')
            hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        cursor=page['next_cursor']
        if not cursor:break
    async def host():
        nonlocal core
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters
        from mcp.types import Implementation
        environment=dict(os.environ);environment['PATH']=str(Path(os.environ['SystemRoot'])/'System32');environment.pop('PYTHONHOME',None);environment.pop('PYTHONPATH',None)
        parameters=StdioServerParameters(command=str(executable),args=['--mcp','--data-dir',str(data)],cwd=executable.parent,env=environment)
        async with Client(parameters,read_timeout_seconds=10,client_info=Implementation(name='AIAssetHub-MCP-Verification',version='0.5.0')) as client:
            tools=await client.list_tools()
            assert {t.name for t in tools.tools}=={'list_libraries','search_assets','get_asset','get_asset_files','get_analysis_status'}
            assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools.tools)
            libraries=await client.call_tool('list_libraries',{});assert not libraries.is_error and libraries.structured_content['items']
            found=await client.call_tool('search_assets',{'query':args.query});assert not found.is_error and found.structured_content['items']
            identifier=found.structured_content['items'][0]['id']
            detail=await client.call_tool('get_asset',{'asset_id':identifier});assert not detail.is_error
            if not args.data_dir:assert 'PRIVATE-PROVENANCE' not in str(detail) and '12345.6789' not in str(detail)
            active=detail.structured_content['activeResult']
            if args.require_analyzed:assert active and active['actualModelId']=='qwen3-vl:2b'
            files=await client.call_tool('get_asset_files',{'asset_id':identifier});assert not files.is_error and files.structured_content['files'][0]['availability']=='present'
            path=Path(files.structured_content['files'][0]['path']);assert path.resolve().is_relative_to((ROOT/'.artifacts').resolve())
            assert str(path.resolve()) in hashes
            status=await client.call_tool('get_analysis_status',{'asset_ids':[identifier]});assert not status.is_error
            assert status.structured_content['items'][0]['hasActiveResult']==bool(active)
            denied=await client.call_tool('search_assets',{'query':'private-query-not-for-audit','filters':{'folder_parts':['..']}});assert denied.is_error
            audit=core.call('mcp.audit');assert any(i['outcome']=='denied' for i in audit['items'])
            assert 'private-query-not-for-audit' not in json.dumps(audit)
            assert core.call('analysis.jobs')==before_jobs and core.call('embedding.status')==before_embeddings
            report={'host':'official Python MCP SDK Client','protocolVersion':client.protocol_version,'server':client.server_info.name,'tools':[t.name for t in tools.tools],'guiOpened':False,'pythonOnPath':False,'assetId':identifier,'activeResultId':active['id'] if active else None,'audit':audit,'noAnalysisOrEmbeddingCreated':True}
            core.close();core=None
            stopped=await client.call_tool('list_libraries',{});assert stopped.is_error and any(code in str(stopped.content) for code in ('APP_NOT_RUNNING','CORE_UNAVAILABLE'))
            report['appStoppedError']=True
            core=helper.InstalledCore(executable,data,args.environment)
            restored=await client.call_tool('get_asset',{'asset_id':identifier});assert not restored.is_error and restored.structured_content['activeResult']==active
            report['restartPreserved']=True;report['restartPidChanged']=core.child.pid!=initial_pid
            report['sourceUnchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in hashes.items());assert report['sourceUnchanged']
        async with Client(parameters,read_timeout_seconds=10,mode='legacy') as legacy:
            legacy_result=await legacy.call_tool('get_asset',{'asset_id':identifier});assert not legacy_result.is_error
            if not args.data_dir:assert 'PRIVATE-PROVENANCE' not in str(legacy_result) and '12345.6789' not in str(legacy_result)
            report['legacyProtocolVersion']=legacy.protocol_version
            report['provenancePrivateDefaultsVerified']=not bool(args.data_dir)
        return report
    try:
        report=asyncio.run(host());report['corePid']=core.child.pid;report['sidecarSha256']=hashlib.sha256(executable.read_bytes()).hexdigest()
        Path(args.report).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
    finally:
        if core:core.close()


if __name__=='__main__':main()
