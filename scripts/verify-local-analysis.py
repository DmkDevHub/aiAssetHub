"""Explicit real-model developer verification; never run by the unit test suite."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import os
import subprocess
import threading
import queue
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-core'))


class InstalledCore:
    def __init__(self, executable, data):
        executable=Path(executable).resolve(strict=True)
        environment=dict(os.environ)
        environment.pop('PYTHONHOME',None);environment.pop('PYTHONPATH',None)
        environment['PATH']=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32')
        self.stderr=open(data.parent/'installed-analysis-stderr.log','ab')
        self.child=subprocess.Popen([str(executable),'--serve','--data-dir',str(data),'--environment','production'],
                                    cwd=executable.parent,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                    stderr=self.stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.responses=queue.Queue()
        def reader():
            while True:
                line=self.child.stdout.readline(16385)
                if not line:self.responses.put(None);return
                self.responses.put(line)
        self.reader=threading.Thread(target=reader,daemon=True);self.reader.start()
        health=self.call('health.get')
        if health['core']['pid']!=self.child.pid:raise RuntimeError('SIDECAR_PID_MISMATCH')

    def call(self, method, params=None):
        identifier=str(uuid4())
        self.child.stdin.write((json.dumps({'request_id':identifier,'method':method,'params':params or {}})+'\n').encode('utf-8'));self.child.stdin.flush()
        frame=self.responses.get(timeout=3)
        if frame is None or len(frame)>16384:raise RuntimeError('SIDECAR_FRAME_INVALID')
        result=json.loads(frame)
        if result['request_id']!=identifier:raise RuntimeError('SIDECAR_REQUEST_MISMATCH')
        if not result['ok']:raise RuntimeError(result['error']['code'])
        return result['data']

    def close(self):
        self.child.stdin.close()
        try:self.child.wait(timeout=10)
        except subprocess.TimeoutExpired:self.child.kill();self.child.wait();raise
        finally:self.stderr.close()
        if self.child.returncode!=0:raise RuntimeError('SIDECAR_EXIT_FAILED')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True);parser.add_argument('--report',required=True);parser.add_argument('--cancel-after',type=float,default=None);parser.add_argument('--sidecar',default=None)
    args=parser.parse_args()
    from PIL import Image,ImageDraw
    from ai_asset_hub_core.runtime import CoreRuntime
    from ai_asset_hub_core.application import CoreApplication
    root=ROOT/'.artifacts'/('real-analysis-'+str(uuid4()));source=root/'source';source.mkdir(parents=True)
    image=Image.new('RGB',(256,256),'white');ImageDraw.Draw(image).rectangle((40,40,216,216),fill='red');path=source/'red-square.png';image.save(path)
    before=hashlib.sha256(path.read_bytes()).hexdigest();runtime=None;app=None;installed=None
    if args.sidecar:installed=InstalledCore(args.sidecar,root/'data')
    else:runtime=CoreRuntime(root/'data','development');app=CoreApplication(runtime.database)
    def call(method,params=None):
        if installed:return installed.call(method,params)
        result=app.handle({'request_id':str(uuid4()),'method':method,'params':params or {}})
        if not result['ok']:raise RuntimeError(result['error']['code'])
        return result['data']
    try:
        library=call('library.register',{'path':str(source)})['library']['id'];call('library.scan',{'library_id':library})
        asset=call('asset.list')['items'][0]['id']
        model=call('model.register',{'provider_name':'Ollama','kind':'local','model_id':args.model,'modalities':['image']})['id']
        inspection=call('model.inspect',{'id':model})
        if inspection['status']!='available' or 'image' not in inspection['modalities']:raise RuntimeError('LOCAL_VISION_MODEL_UNAVAILABLE')
        call('model.policy',{'id':model,'enabled':True,'allow_external':False,'allow_paid':False,'budget_usd':'0','max_requests':10})
        plan={'mode':'selected','scope':'all','library_id':None,'folder_parts':[],'selected_ids':[asset],'model_id':model}
        preview=call('analysis.preview',plan)
        job=call('analysis.start',{'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
        deadline=time.monotonic()+300;started=time.monotonic()
        cancel_sent=False
        while True:
            status=call('analysis.status',{'job_id':job})
            if status['status'] in ('completed','failed','canceled'):break
            if args.cancel_after is not None and not cancel_sent and time.monotonic()-started>=args.cancel_after:
                call('analysis.cancel',{'job_id':job});cancel_sent=True
            if time.monotonic()>deadline:raise RuntimeError('VERIFICATION_TIMEOUT')
            time.sleep(1)
        active=call('asset.analysis',{'asset_id':asset})['active']
        report={'model':args.model,'registryId':model,'jobId':job,'assetId':asset,'status':status,'active':active,
                'elapsedSeconds':round(time.monotonic()-started,2),'sourceUnchanged':hashlib.sha256(path.read_bytes()).hexdigest()==before,
                'database':call('health.get')['database'],'cancelRequested':cancel_sent,'guiOpened':False}
        if installed:
            installed.close();installed=InstalledCore(args.sidecar,root/'data')
            reopened=call('asset.analysis',{'asset_id':asset})['active']
            report['restartPreserved']=reopened==active and len(call('analysis.jobs')['items'])==1
            if not report['restartPreserved']:raise RuntimeError('INSTALLED_RESTART_LOST_RESULT')
            report['sidecarSha256']=hashlib.sha256(Path(args.sidecar).read_bytes()).hexdigest()
            installed.close();installed=None;report['coreProcessesStopped']=True
            if (root/'installed-analysis-stderr.log').stat().st_size:raise RuntimeError('UNEXPECTED_INSTALLED_STDERR')
        Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':status['status'],'elapsedSeconds':report['elapsedSeconds'],'sourceUnchanged':report['sourceUnchanged']}),flush=True)
        if status['status']!=('canceled' if args.cancel_after is not None else 'completed') or args.cancel_after is None and not active or not report['sourceUnchanged']:raise RuntimeError('REAL_ANALYSIS_FAILED')
    finally:
        if installed:installed.close()
        if app:app.close()
        if runtime:runtime.close()


if __name__=='__main__':main()
