"""Explicit real local-model verification; not part of automatic unit tests."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-core'))
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('local_verification',ROOT/'scripts/verify-local-analysis.py')
helper=module_from_spec(spec);spec.loader.exec_module(helper)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--embedding-model',required=True);parser.add_argument('--analysis-model',default='qwen3-vl:2b');parser.add_argument('--report',required=True);parser.add_argument('--sidecar')
    args=parser.parse_args()
    from PIL import Image,ImageDraw
    from ai_asset_hub_core.runtime import CoreRuntime
    from ai_asset_hub_core.application import CoreApplication
    root=ROOT/'.artifacts'/('semantic-real-'+str(uuid4()));source=root/'source';source.mkdir(parents=True)
    for name in ('torch','tree','water'):
        image=Image.new('RGB',(256,256),'white');draw=ImageDraw.Draw(image)
        if name=='torch':
            draw.rectangle((116,110,140,236),fill='#75411e');draw.polygon([(128,16),(88,92),(104,132),(150,132),(170,72),(144,92)],fill='#f56b16');draw.polygon([(128,55),(111,104),(125,127),(145,102)],fill='#ffda33')
        elif name=='tree':
            draw.rectangle((116,120,140,236),fill='#75411e');draw.polygon([(128,18),(32,188),(224,188)],fill='#178d35')
        else:
            draw.rectangle((0,80,256,256),fill='#238cd8')
            for y in range(100,240,35):draw.arc((20,y,100,y+30),0,180,fill='white',width=4);draw.arc((130,y,220,y+30),0,180,fill='white',width=4)
        image.save(source/(name+'.png'))
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    client=helper.InstalledCore(args.sidecar,root/'data') if args.sidecar else None
    runtime=CoreRuntime(root/'data','development') if not client else None
    app=CoreApplication(runtime.database) if runtime else None
    def call(method,params=None):
        if client:return client.call(method,params)
        response=app.handle({'request_id':str(uuid4()),'method':method,'params':params or {}})
        if not response['ok']:raise RuntimeError(response['error']['code'])
        return response['data']
    def wait(method,job):
        deadline=time.monotonic()+600
        while True:
            status=call(method,{'job_id':job})
            if status['status'] not in ('queued','running'):
                if status['status']!='completed':raise RuntimeError(json.dumps(status))
                return status
            if time.monotonic()>deadline:raise RuntimeError('VERIFICATION_TIMEOUT')
            time.sleep(.5)
    try:
        library=call('library.register',{'path':str(source)})['library']['id'];call('library.scan',{'library_id':library})
        assets=[];cursor=None
        while True:
            page=call('asset.list',{'after_id':cursor});assets.extend(page['items']);cursor=page['next_cursor']
            if not cursor:break
        model=call('model.register',{'provider_name':'Ollama','kind':'local','model_id':args.analysis_model,'modalities':['image']})['id']
        call('model.inspect',{'id':model});call('model.policy',{'id':model,'enabled':True,'allow_external':False,'allow_paid':False,'budget_usd':'0','max_requests':10})
        plan={'mode':'all','scope':'all','library_id':None,'folder_parts':[],'selected_ids':[],'model_id':model}
        preview=call('analysis.preview',plan)
        job=call('analysis.start',{'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId'];wait('analysis.status',job)
        print('Local image analysis completed for three test-owned PNGs.',flush=True)
        captions={a['name']:call('asset.analysis',{'asset_id':a['id']})['active'] for a in assets}
        configured=call('embedding.configure',{'model_name':args.embedding_model,'prefix_scheme':'embeddinggemma'})['profile']
        pairs=[{'asset_id':a['id'],'result_id':captions[a['name']]['id']} for a in assets]
        wait('embedding.work',call('embedding.start',{'selected':pairs,'confirmed':True})['jobId'])
        assert call('embedding.status')['readyCount']==3
        print('Three real document embeddings stored.',flush=True)
        queries=[]
        for query,target in [('중세 마을 횃불','torch.png'),('숲에서 쓸 만한 나무','tree.png'),('푸른 바다의 물결','water.png')]:
            result=wait('embedding.work',call('embedding.query',{'query':query,'mode':'semantic','confirmed':True})['jobId'])['results']
            expected=next(a['id'] for a in assets if a['name']==target)
            queries.append({'query':query,'expected':expected,'results':result})
            if not result or result[0]['id']!=expected:raise RuntimeError('KOREAN_RETRIEVAL_MISMATCH: '+json.dumps(queries,ensure_ascii=False))
        print('Korean retrieval top-1 checks passed: 3/3.',flush=True)
        tree=next(a['id'] for a in assets if a['name']=='tree.png');call('asset.tags',{'asset_id':tree,'add':['tree','forest-fixture'],'remove':[]})
        hybrid=wait('embedding.work',call('embedding.query',{'query':'tree','mode':'hybrid','confirmed':True,'criteria':{'tag':'forest-fixture'}})['jobId'])['results']
        assert hybrid and hybrid[0]['id']==tree and hybrid[0]['reason']=='hybrid'
        changed=call('embedding.configure',{'model_name':args.embedding_model,'prefix_scheme':'plain'})['profile'];assert changed['version']!=configured['version'] and call('embedding.status')['readyCount']==0
        wait('embedding.work',call('embedding.rebuild',{'confirmed':True})['jobId']);assert call('embedding.status')['readyCount']==3
        call('embedding.configure',{'model_name':args.embedding_model,'prefix_scheme':'embeddinggemma'});assert call('embedding.status')['readyCount']==3
        report={'profile':configured,'captions':captions,'queries':queries,'hybrid':hybrid,'versionIsolation':True,'atomicRebuild':True,'sourceUnchanged':hashes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()},'guiOpened':False}
        if not report['sourceUnchanged']:raise RuntimeError('SOURCE_CHANGED')
        if client:
            client.close();client=helper.InstalledCore(args.sidecar,root/'data');report['restartReadyCount']=call('embedding.status')['readyCount'];assert report['restartReadyCount']==3
        Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'koreanTop1':len(queries),'sourceUnchanged':report['sourceUnchanged'],'dimension':configured['dimension']}),flush=True)
    finally:
        if client:client.close()
        if app:app.close()
        if runtime:runtime.close()


if __name__=='__main__':main()
