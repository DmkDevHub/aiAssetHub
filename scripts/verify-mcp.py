"""Real reference Host -> packaged stdio Bridge -> running packaged Core, no GUI/AI."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import time
import hashlib
import atexit
from uuid import uuid4
from importlib.util import spec_from_file_location,module_from_spec

ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location('local_verification',ROOT/'scripts/verify-local-analysis.py')
helper=module_from_spec(spec);spec.loader.exec_module(helper)


def extension_fixture(core,source,library,creator):
    (source/'mesh.obj').write_bytes(b'mtllib registered.mtl missing.mtl https://example.invalid/PRIVATE-DEPENDENCY\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    (source/'registered.mtl').write_bytes(b'fixture material')
    core.call('library.scan',{'library_id':library})
    assets={};cursor=None
    while True:
        page=core.call('asset.list',{'after_id':cursor})
        assets.update({Path(a['path']).name:a['id'] for a in page['items']});cursor=page['next_cursor']
        if cursor is None:break
    asset=assets['mesh.obj']
    group=core.call('asset.groups.create',{'value':dict(name='확장 검증 그룹',description='')})['id']
    package=core.call('asset.packages.create',{'value':dict(name='확장 검증 패키지',description='',unit='distribution',version='',purchase=dict(amount=None,currency='',date=''))})['id']
    core.call('asset.groups.assign',dict(asset_id=asset,group_ids=[group],expected_revision=0))
    core.call('asset.packages.assign',dict(asset_id=asset,package_ids=[package],expected_revision=0))
    core.call('creator.links.save',dict(subject=dict(kind='package',id=package),links=[dict(creator_id=creator['id'],role='producer')],expected_revision=0))
    classification=core.call('catalog.classification',dict(asset_id=asset))['value'];classification['primary']='A02'
    core.call('catalog.classification.save',dict(asset_id=asset,value=classification,expected_revision=0,confirmed=True))
    core.call('license.create',dict(subject=dict(kind='package',id=package),confirmed=True,value=dict(label='Declared package license',terms='PRIVATE-PROVENANCE-TERMS',attribution='PRIVATE-PROVENANCE-CREDIT',reviewStatus='user_reviewed',scope='fixture',note='PRIVATE-PROVENANCE-NOTE',source_id=None)))
    core.call('asset.technical.collect',dict(asset_id=asset,confirmed=True))
    own=core.call('asset.composition',dict(asset_id=asset))['value']['files'][0]['fileId']
    dep=core.call('asset.composition',dict(asset_id=assets['registered.mtl']))['value']['files'][0]['fileId']
    core.call('asset.composition.save',dict(asset_id=asset,expected_revision=0,value=dict(files=[dict(fileId=own,role='source'),dict(fileId=dep,role='dependency')],components=[])))
    return dict(asset=asset,group=group,package=package,creator=creator['id'],sourceFile=own,dependencyFile=dep)


async def check_extensions(client,fixture):
    request=dict(query='fixture creator',schema_version=2,filters=dict(types=['A02'],group_ids=[fixture['group']],package_ids=[fixture['package']],creator_ids=[fixture['creator']],creator_roles=['producer']))
    found=await client.call_tool('search_assets',request);assert not found.is_error
    assert [i['id'] for i in found.structured_content['items']]==[fixture['asset']]
    item=found.structured_content['items'][0]
    assert item['metadata']['classification']['value']['primary']=='A02'
    assert item['metadata']['creators'][0]['subjectId']==fixture['package']
    detail=await client.call_tool('get_asset',dict(asset_id=fixture['asset'],schema_version=2));assert not detail.is_error
    planning=detail.structured_content['unityPlanning']
    assert planning['rights']['permission']=='unknown' and planning['rights']['declarations'][0]['reviewStatus']=='user_reviewed'
    assert not planning['executable'] and not planning['compatibility']['editorVerified']
    files=await client.call_tool('get_asset_files',dict(asset_id=fixture['asset'],schema_version=2));assert not files.is_error
    state=files.structured_content;assert len(state['files'])==2 and state['availability']=='available'
    source=next(f for f in state['files'] if f['id']==fixture['sourceFile'])
    assert source['technical']['observation']['value']['vertexCount']==3 and not source['technical']['stale']
    assert sorted(d['status'] for d in source['dependencies']['items'])==['blocked','present','unresolved']
    assert next(d for d in source['dependencies']['items'] if d['status']=='present')['fileId']==fixture['dependencyFile']
    assert len(state['components'])==1 and state['components'][0]['fileId']==fixture['sourceFile']
    for value in (found,detail,files):assert 'PRIVATE-' not in str(value) and '12345.6789' not in str(value)
    return dict(assetId=fixture['asset'],componentId=state['components'][0]['id'],metadata=detail.structured_content['metadata'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core',required=True);parser.add_argument('--report',required=True);parser.add_argument('--data-dir');parser.add_argument('--environment',choices=['development','production'],default='production');parser.add_argument('--query',default='mcp-fixture');parser.add_argument('--require-analyzed',action='store_true');args=parser.parse_args()
    executable=Path(args.core).resolve(strict=True);root=ROOT/'.artifacts'/('mcp-real-'+str(uuid4()));root.mkdir()
    data=Path(args.data_dir).resolve() if args.data_dir else root/'data'
    if not data.is_relative_to((ROOT/'.artifacts').resolve()):raise RuntimeError('TEST_DATA_MUST_BE_OWNED_ARTIFACT')
    core=helper.InstalledCore(executable,data,args.environment);initial_pid=core.child.pid
    def cleanup():
        if core and core.child.poll() is None:core.close()
    atexit.register(cleanup)
    extension=None
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
        extension=extension_fixture(core,source,library,creator)

    before_jobs=core.call('analysis.jobs');before_embeddings=core.call('embedding.status')
    catalog_verified=False
    if not args.data_dir:
        found=core.call('catalog.query',{'query':'fixture creator','criteria':{'creator_ids':[creator['id']],'creator_roles':['creator'],'purchase_status':['paid'],'purchase_currency':'KRW'},'after_id':None,'sort':'creator'})
        assert found['ids']==[fixture_id] and found['inferenceCalled'] is False
        assert core.call('catalog.order',{'asset_ids':[fixture_id],'sort':'size_desc'})['ids']==[fixture_id]
        assert core.call('catalog.query',{'query':'PRIVATE-PROVENANCE','criteria':{},'after_id':None,'sort':'name'})['ids']==[]
        assert core.call('analysis.jobs')==before_jobs and core.call('embedding.status')==before_embeddings
        catalog_verified=True
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
            extension_result=await check_extensions(client,extension) if extension else None
            if extension:
                dependency_path=source/'registered.mtl';held=root/'held-fixture.mtl'
                dependency_path.rename(held)
                try:
                    missing=await client.call_tool('get_asset_files',dict(asset_id=extension['asset'],schema_version=2))
                    assert not missing.is_error and missing.structured_content['availability']=='partial'
                    assert next(f for f in missing.structured_content['files'] if f['id']==extension['dependencyFile'])['availability']=='missing'
                finally:held.rename(dependency_path)
                unknown=await client.call_tool('get_asset',dict(asset_id=str(uuid4()),schema_version=2));assert unknown.is_error
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
            if extension:
                # Installed Broker authentication and write denial, without exposing secrets.
                import socket
                from ai_asset_hub_core.session_file import read
                from ai_asset_hub_core.mcp_broker import encode,receive,BrokerClient,BrokerError
                session=read(data)
                request=dict(session=session['session'],request_id=str(uuid4()),host='reference-host',tool='_health',arguments={},mac='0'*64)
                with socket.create_connection(('127.0.0.1',session['port']),timeout=2) as connection:
                    connection.sendall(encode(request));assert receive(connection)['error']=='AUTH_DENIED'
                try:BrokerClient(data).call('analysis.start',{})
                except BrokerError as error:assert str(error)=='MCP_TOOL_NOT_ALLOWED'
                else:raise AssertionError('WRITE_NOT_DENIED')
                report['installedAuthAndWriteDenial']=True
                report['extendedSearchCompositionRightsVerified']=True
                report['registeredMissingDependencyVerified']=True
                auth_audit=core.call('mcp.audit')
                assert any(i['errorCode']=='AUTH_DENIED' for i in auth_audit['items'])
                assert any(i['errorCode']=='MCP_TOOL_NOT_ALLOWED' for i in auth_audit['items'])
                assert session['token'] not in json.dumps(auth_audit) and 'PRIVATE-' not in json.dumps(auth_audit)
                report['audit']=auth_audit
                assert core.call('analysis.jobs')==before_jobs and core.call('embedding.status')==before_embeddings
            core.close();core=None
            stopped=await client.call_tool('list_libraries',{});assert stopped.is_error and any(code in str(stopped.content) for code in ('APP_NOT_RUNNING','CORE_UNAVAILABLE'))
            report['appStoppedError']=True
            core=helper.InstalledCore(executable,data,args.environment)
            restored=await client.call_tool('get_asset',{'asset_id':identifier});assert not restored.is_error and restored.structured_content['activeResult']==active
            if extension:assert await check_extensions(client,extension)==extension_result
            report['restartPreserved']=True;report['restartPidChanged']=core.child.pid!=initial_pid
            report['sourceUnchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in hashes.items());assert report['sourceUnchanged']
        async with Client(parameters,read_timeout_seconds=10,mode='legacy') as legacy:
            legacy_result=await legacy.call_tool('get_asset',{'asset_id':identifier});assert not legacy_result.is_error
            if not args.data_dir:assert 'PRIVATE-PROVENANCE' not in str(legacy_result) and '12345.6789' not in str(legacy_result)
            report['legacyProtocolVersion']=legacy.protocol_version
            if extension:
                assert await check_extensions(legacy,extension)==extension_result
                report['legacyExtendedContractVerified']=True
            report['provenancePrivateDefaultsVerified']=not bool(args.data_dir)
            report['catalogFiltersAndSortVerified']=catalog_verified
        return report
    try:
        report=asyncio.run(host());report['corePid']=core.child.pid;report['sidecarSha256']=hashlib.sha256(executable.read_bytes()).hexdigest()
        Path(args.report).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
    finally:
        if core:core.close()


if __name__=='__main__':main()
