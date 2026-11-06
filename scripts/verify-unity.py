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
        (project/'finish.test').write_text('done');assert process.wait(timeout=30)==0
        report=dict(passed=True,editorVersion=state['editorVersion'],project=str(project),actualEditorPid=state['pid'],pingSucceeded=True,
            imported=imported,sourcePreserved=True,guiOpened=False,inferenceCalls=0,elapsedSeconds=round(time.monotonic()-started,3),verifiedAt=datetime.now(timezone.utc).isoformat())
        Path(args.report).write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:
        database.close()
        if process and process.poll() is None:process.terminate();process.wait(timeout=20)


if __name__=='__main__':main()
