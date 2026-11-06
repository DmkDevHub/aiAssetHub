"""Installed Core + actual stdio SDK Host + shipped package + real headless Unity.

All files/projects/data are owned fixtures. No GUI, AI model, user assets or scene save.
"""
import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import Implementation
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('unity_installed_helper',ROOT/'scripts/verify-local-analysis.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


async def scenario(args,core,root,project,source,assets,target):
    environment=dict(os.environ);environment['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
    environment.pop('PYTHONHOME',None);environment.pop('PYTHONPATH',None)
    parameters=StdioServerParameters(command=str(Path(args.core).resolve()),args=['--mcp','--data-dir',str(root/'data')],cwd=Path(args.core).resolve().parent,env=environment)
    async with Client(parameters,read_timeout_seconds=10,client_info=Implementation(name='AIAssetHub-MCP-Verification',version='0.5.0')) as client:
        async def call(tool,params):
            result=await client.call_tool(tool,params)
            assert not result.is_error,(tool,result.content)
            return result.structured_content
        async def terminal(identifier):
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                status=await call('get_operation_status',dict(operation_id=identifier))
                if status['status'] not in ('queued','unknown'):return status
                await asyncio.sleep(.15)
            raise RuntimeError('UNITY_HOST_RESULT_TIMEOUT')
        async def pause():
            (project/'pause.test').write_text('pause')
            deadline=time.monotonic()+5
            while not (project/'paused.test').exists():
                assert time.monotonic()<deadline
                await asyncio.sleep(.1)
        def approval(plan):return dict(plan_id=plan['planId'],request_id=str(uuid4()),confirmed=True,rights_confirmed=True,compatibility_confirmed=True)
        tools=(await client.list_tools()).tools
        assert len(tools)==12
        targets=await call('list_unity_targets',{})
        row=next(r for r in targets['items'] if r['id']==target);assert row['connected'] and row['batchMode']
        assert Path(targets['connectorPackagePath']).resolve()==Path(args.package).resolve()/'package.json'
        # Scripted Host interprets the scenario "숲 배경 에셋을 Unity 씬 (2,3,0)에 배치".
        # This is a reference-host fixture, not an external product/model inference test.
        search=await call('search_assets',dict(query='숲',schema_version=2))
        assert [r['id'] for r in search['items']]==[assets['숲']]
        asset=search['items'][0]['id']
        detail=await call('get_asset',dict(asset_id=asset,schema_version=2));assert detail['unityPlanning']['rights']['permission']=='unknown'
        files=await call('get_asset_files',dict(asset_id=asset,schema_version=2));assert files['files'][0]['availability']=='present'
        plan=await call('preview_unity_import',dict(target_id=target,asset_ids=[asset]))
        denied=await client.call_tool('import_assets_to_unity',{**approval(plan),'confirmed':False});assert denied.is_error
        request=approval(plan);queued=await call('import_assets_to_unity',request)
        imported=await terminal(queued['operationId']);assert imported['status']=='succeeded',imported
        duplicate=await call('import_assets_to_unity',request);assert duplicate['operationId']==imported['operationId']
        item=imported['result']['items'][0];assert (project/item['assetPath']).read_bytes()==(source/'숲.png').read_bytes()
        await asyncio.sleep(.3)
        placement=await call('preview_unity_placement',dict(target_id=target,import_operation_id=imported['operationId'],position=[2,3,0],rotation=[0,0,30],scale=[2,2,1],name='숲 Sprite'))
        placed=await terminal((await call('place_assets_in_unity',approval(placement)))['operationId']);assert placed['status']=='succeeded',placed
        assert placed['result']['items'][0]['position']==[2,3,0] and placed['result']['items'][0]['sceneSaved'] is False
        await pause()
        batch_plan=await call('preview_unity_import',dict(target_id=target,asset_ids=[assets['batch-ok'],assets['batch-conflict']]))
        batch=await call('import_assets_to_unity',approval(batch_plan))
        conflict=project/batch_plan['items'][1]['targetRelativePath'];conflict.write_bytes((source/'batch-conflict.png').read_bytes());conflict_hash=hashlib.sha256(conflict.read_bytes()).hexdigest()
        (project/'pause.test').unlink();partial=await terminal(batch['operationId'])
        assert partial['status']=='partial' and [r['status'] for r in partial['result']['items']]==['succeeded','failed']
        assert partial['result']['items'][1]['errorCode']=='UNITY_TARGET_CONFLICT' and hashlib.sha256(conflict.read_bytes()).hexdigest()==conflict_hash
        # Wait until harness has cleared its acknowledgement, then pause again.
        deadline=time.monotonic()+5
        while (project/'paused.test').exists():
            assert time.monotonic()<deadline
            await asyncio.sleep(.1)
        await pause()
        cancel_plan=await call('preview_unity_import',dict(target_id=target,asset_ids=[assets['cancel-a'],assets['cancel-b']]))
        cancel_op=await call('import_assets_to_unity',approval(cancel_plan))
        requested=await call('cancel_unity_operation',dict(operation_id=cancel_op['operationId'],confirmed=True))
        assert requested['cancelRequested'] and requested['status']=='queued'
        (project/'pause.test').unlink();cancelled=await terminal(cancel_op['operationId'])
        assert cancelled['status']=='cancelled' and all(i['status']=='cancelled' for i in cancelled['result']['items'])
        assert all(not (project/i['targetRelativePath']).exists() for i in cancel_plan['items'])
        return dict(protocol=client.protocol_version,toolCount=len(tools),imported=imported,placed=placed,partial=partial,cancelled=cancelled,searchAssetId=asset)


async def check_restart(args,root,expected):
    parameters=StdioServerParameters(command=str(Path(args.core).resolve()),args=['--mcp','--data-dir',str(root/'data')],cwd=Path(args.core).resolve().parent)
    async with Client(parameters,read_timeout_seconds=10) as client:
        for key in ('imported','placed','partial','cancelled'):
            result=await client.call_tool('get_operation_status',dict(operation_id=expected[key]['operationId']))
            assert not result.is_error and result.structured_content==expected[key]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--editor',required=True);parser.add_argument('--core',required=True);parser.add_argument('--package',required=True);parser.add_argument('--report',required=True);args=parser.parse_args()
    root=ROOT/'.artifacts'/('m09-installed-'+str(uuid4()));project=root/'project';source=root/'source'
    (project/'Assets/Editor').mkdir(parents=True);(project/'ProjectSettings').mkdir();(project/'Packages').mkdir();source.mkdir()
    (project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: '+Path(args.editor).parents[1].name+'\n')
    (project/'Packages/manifest.json').write_text(json.dumps(dict(dependencies={'local.aiassethub.editor':'file:'+str(Path(args.package).resolve()).replace('\\','/')})))
    shutil.copyfile(ROOT/'unity-package/Tests~/BatchHarness.cs',project/'Assets/Editor/BatchHarness.cs')
    outside=root/'junction-target';outside.mkdir();junction=root/'dangling-junction'
    linked=subprocess.run(['cmd','/c','mklink','/J',str(junction),str(outside)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    assert linked.returncode==0
    outside.rmdir();(project/'unsafe-path.test').write_text(str(junction))
    for name in ('숲','batch-ok','batch-conflict','cancel-a','cancel-b'):Image.new('RGBA',(4,4),(12,100,44,255)).save(source/(name+'.png'))
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    core=None;process=None;started=time.monotonic()
    try:
        core=helper.InstalledCore(args.core,root/'data');call=core.call
        library=call('library.register',dict(path=str(source)))['library']['id'];call('library.scan',dict(library_id=library));assets={};cursor=None
        while True:
            page=call('asset.list',dict(after_id=cursor));assets.update({Path(a['path']).stem:a['id'] for a in page['items']});cursor=page['next_cursor']
            if cursor is None:break
        target=call('unity.target.save',dict(project_path=str(project),confirmed=True))['id']
        process=subprocess.Popen([args.editor,'-batchmode','-nographics','-projectPath',str(project),'-executeMethod','AIAssetHub.Editor.BatchHarness.Run','-logFile',str(root/'unity.log')],
            creationflags=subprocess.CREATE_NO_WINDOW,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+120
        while True:
            assert process.poll() is None,'UNITY_EXITED_DURING_STARTUP'
            target_state=call('unity.targets',{})['items'][0]
            if target_state['connected']:break
            assert time.monotonic()<deadline,'UNITY_HOST_CONNECT_TIMEOUT'
            time.sleep(.15)
        assert target_state['pid']==process.pid
        jobs=call('analysis.jobs',{});embedding=call('embedding.status',{})
        result=asyncio.run(scenario(args,core,root,project,source,assets,target))
        assert call('analysis.jobs',{})==jobs and call('embedding.status',{})==embedding
        # Audit must retain fixed actions, with no paths, command bodies or tokens.
        audit=call('mcp.audit',{})
        assert any(i['tool']=='get_operation_status' for i in audit['items'])
        assert all(term not in json.dumps(audit) for term in ('sourcePath','token','sha256',str(project),'숲 Sprite'))
        core.close();core=None;core=helper.InstalledCore(args.core,root/'data');call=core.call
        asyncio.run(check_restart(args,root,result))
        assert call('unity.targets',{})['items'][0]['id']==target and len(call('unity.operations',{})['items'])==4
        assert call('analysis.jobs',{})==jobs and call('embedding.status',{})==embedding
        assert all(hashlib.sha256((source/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())
        (project/'expect-placement.test').write_text('yes');(project/'finish.test').write_text('done');assert process.wait(timeout=30)==0
        result.update(passed=True,editorVersion=target_state['editorVersion'],actualEditorPid=process.pid,project=str(project),
            editorAssertions=json.loads((project/'editor-assertions.json').read_text()),coreRestartPreserved=True,sourceHashesPreserved=True,
            pathAssertions=json.loads((project/'path-assertions.json').read_text()),
            auditRedacted=True,inferenceCalls=0,guiOpened=False,sidecarSha256=hashlib.sha256(Path(args.core).read_bytes()).hexdigest(),
            connectorSha256=hashlib.sha256((Path(args.package)/'Editor/Connector.cs').read_bytes()).hexdigest(),
            elapsedSeconds=round(time.monotonic()-started,3),verifiedAt=datetime.now(timezone.utc).isoformat())
        Path(args.report).write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
    finally:
        if core:core.close()
        if process and process.poll() is None:process.terminate();process.wait(timeout=20)
        if junction.is_junction():junction.rmdir()


if __name__=='__main__':main()
