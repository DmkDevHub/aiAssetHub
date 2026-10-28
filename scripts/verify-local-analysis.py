"""Explicit real-model developer verification; never run by the unit test suite."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-core'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True);parser.add_argument('--report',required=True)
    args=parser.parse_args()
    from PIL import Image,ImageDraw
    from ai_asset_hub_core.runtime import CoreRuntime
    from ai_asset_hub_core.application import CoreApplication
    root=ROOT/'.artifacts'/('real-analysis-'+str(uuid4()));source=root/'source';source.mkdir(parents=True)
    image=Image.new('RGB',(256,256),'white');ImageDraw.Draw(image).rectangle((40,40,216,216),fill='red');path=source/'red-square.png';image.save(path)
    before=hashlib.sha256(path.read_bytes()).hexdigest();runtime=CoreRuntime(root/'data','development');app=CoreApplication(runtime.database)
    def call(method,params=None):
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
        while True:
            status=call('analysis.status',{'job_id':job})
            if status['status'] in ('completed','failed','canceled'):break
            if time.monotonic()>deadline:raise RuntimeError('VERIFICATION_TIMEOUT')
            time.sleep(1)
        active=call('asset.analysis',{'asset_id':asset})['active']
        report={'model':args.model,'registryId':model,'jobId':job,'assetId':asset,'status':status,'active':active,
                'elapsedSeconds':round(time.monotonic()-started,2),'sourceUnchanged':hashlib.sha256(path.read_bytes()).hexdigest()==before,
                'database':app.health()['database'],'guiOpened':False}
        Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':status['status'],'elapsedSeconds':report['elapsedSeconds'],'sourceUnchanged':report['sourceUnchanged']}),flush=True)
        if status['status']!='completed' or not active or not report['sourceUnchanged']:raise RuntimeError('REAL_ANALYSIS_FAILED')
    finally:app.close();runtime.close()


if __name__=='__main__':main()
