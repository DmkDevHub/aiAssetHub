"""Owned temporary Unity project, real batchmode Editor, no GUI/input automation."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-core'))
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.unity_connector import EditorMailbox
from ai_asset_hub_core.libraries import LibraryError
from ai_asset_hub_core.libraries import LibraryService
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.unity_targets import UnityTargets
from ai_asset_hub_core.unity_operations import UnityOperations


def await_value(action,timeout=120):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            result=action()
            if result:return result
        except (LibraryError,FileNotFoundError):pass
        time.sleep(.15)
    raise RuntimeError('UNITY_VERIFICATION_TIMEOUT')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--editor',required=True);parser.add_argument('--report',required=True);args=parser.parse_args()
    root=ROOT/'.artifacts'/('m09-unity-'+str(uuid4()));project=root/'project'
    (project/'Assets/Editor').mkdir(parents=True);(project/'Packages').mkdir();(project/'ProjectSettings').mkdir()
    version=Path(args.editor).parents[1].name
    (project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: '+version+'\n')
    (project/'Packages/manifest.json').write_text(json.dumps(dict(dependencies={'local.aiassethub.editor':'file:'+str(ROOT/'unity-package').replace('\\','/')})))
    shutil.copyfile(ROOT/'unity-package/Tests~/BatchHarness.cs',project/'Assets/Editor/BatchHarness.cs')
    database=Database(root/'test.sqlite');process=None;started=time.monotonic()
    try:
        process=subprocess.Popen([args.editor,'-batchmode','-nographics','-projectPath',str(project),'-executeMethod','AIAssetHub.Editor.BatchHarness.Run','-logFile',str(root/'unity.log')],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        mailbox=EditorMailbox(database,[project]);directory,state=await_value(lambda:mailbox.connect(str(project)))
        identifier,session=mailbox.send(str(project),'ping')
        result=await_value(lambda:mailbox.result(str(project),identifier,session),15)
        assert result['status']=='succeeded' and state['pid']==process.pid and state['batchMode']
        assert 'token' not in mailbox.public(state)
        from PIL import Image
        source=root/'source';source.mkdir();Image.new('RGBA',(4,4),(12,100,44,255)).save(source/'숲.png')
        library=LibraryService(database).register(dict(path=str(source)))['library']['id'];AssetService(database).scan(dict(library_id=library))
        asset=AssetService(database).list({})['items'][0]['id']
        target=UnityTargets(database).save(dict(project_path=str(project),confirmed=True))['id']
        service=UnityOperations(database);plan=service.preview_import(dict(target_id=target,asset_ids=[asset]))
        operation=service.execute_import(dict(plan_id=plan['planId'],request_id=str(uuid4()),confirmed=True,rights_confirmed=True,compatibility_confirmed=True))
        def completed():
            status=service.status(dict(operation_id=operation['operationId']))
            return status if status['status'] not in ('queued','unknown') else None
        imported=await_value(completed,30)
        assert imported['status']=='succeeded',imported
        item=imported['result']['items'][0]
        assert (project/item['assetPath']).read_bytes()==(source/'숲.png').read_bytes() and len(item['guid'])==32
        time.sleep(.3)
        place_plan=service.preview_place(dict(target_id=target,import_operation_id=imported['operationId'],position=[2,3,0],rotation=[0,0,30],scale=[2,2,1],name='숲 Sprite'))
        placed_op=service.execute_place(dict(plan_id=place_plan['planId'],request_id=str(uuid4()),confirmed=True,rights_confirmed=True,compatibility_confirmed=True))
        def placement_completed():
            status=service.status(dict(operation_id=placed_op['operationId']))
            return status if status['status'] not in ('queued','unknown') else None
        placed=await_value(placement_completed,20);assert placed['status']=='succeeded',placed
        assert placed['result']['items'][0]['position']==[2,3,0] and placed['result']['items'][0]['sceneSaved'] is False
        extra={}
        for name in ('batch-ok','batch-conflict','cancel-a','cancel-b'):
            Image.new('RGBA',(4,4),(77,33,88,255)).save(source/(name+'.png'))
        AssetService(database).scan(dict(library_id=library))
        extra={};cursor=None
        while True:
            page=AssetService(database).list(dict(after_id=cursor));extra.update({Path(a['path']).stem:a['id'] for a in page['items']});cursor=page['next_cursor']
            if cursor is None:break
        def terminal(identifier):
            status=service.status(dict(operation_id=identifier))
            return status if status['status'] not in ('queued','unknown') else None
        (project/'pause.test').write_text('pause');await_value(lambda:(project/'paused.test').exists(),5)
        batch_plan=service.preview_import(dict(target_id=target,asset_ids=[extra['batch-ok'],extra['batch-conflict']]))
        batch=service.execute_import(dict(plan_id=batch_plan['planId'],request_id=str(uuid4()),confirmed=True,rights_confirmed=True,compatibility_confirmed=True))
        conflict=project/batch_plan['items'][1]['targetRelativePath'];conflict.write_bytes(b'owned existing conflict')
        (project/'pause.test').unlink();partial=await_value(lambda:terminal(batch['operationId']),20)
        assert partial['status']=='partial' and [i['status'] for i in partial['result']['items']]==['succeeded','failed'],partial
        assert partial['result']['items'][1]['errorCode']=='UNITY_TARGET_CONFLICT' and conflict.read_bytes()==b'owned existing conflict'
        (project/'pause.test').write_text('pause');await_value(lambda:(project/'paused.test').exists(),5)
        cancel_plan=service.preview_import(dict(target_id=target,asset_ids=[extra['cancel-a'],extra['cancel-b']]))
        cancel_op=service.execute_import(dict(plan_id=cancel_plan['planId'],request_id=str(uuid4()),confirmed=True,rights_confirmed=True,compatibility_confirmed=True))
        requested=service.cancel(dict(operation_id=cancel_op['operationId'],confirmed=True));assert requested['cancelRequested'] and requested['status']=='queued'
        (project/'pause.test').unlink();cancelled=await_value(lambda:terminal(cancel_op['operationId']),20)
        assert cancelled['status']=='cancelled' and all(i['status']=='cancelled' for i in cancelled['result']['items']),cancelled
        assert all(not (project/i['targetRelativePath']).exists() for i in cancel_plan['items'])
        (project/'expect-placement.test').write_text('yes')
        (project/'finish.test').write_text('done');assert process.wait(timeout=30)==0
        editor_assertions=json.loads((project/'editor-assertions.json').read_text())
        report=dict(passed=True,editorVersion=state['editorVersion'],project=str(project),actualEditorPid=state['pid'],pingSucceeded=True,
            imported=imported,placed=placed,partial=partial,cancelled=cancelled,editorAssertions=editor_assertions,sourcePreserved=True,guiOpened=False,inferenceCalls=0,elapsedSeconds=round(time.monotonic()-started,3),verifiedAt=datetime.now(timezone.utc).isoformat())
        Path(args.report).write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:
        database.close()
        if process and process.poll() is None:process.terminate();process.wait(timeout=20)


if __name__=='__main__':main()
