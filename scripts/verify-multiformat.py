"""Installed Core verification with real file parsers and a labelled fake local provider.

Never downloads models, calls external APIs, opens a GUI, or uses a user database.
The loopback provider is a deterministic transport fixture, NOT a real AI model.
"""
import argparse
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import threading
import time
import wave
import zipfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from uuid import uuid4
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
MODEL='m08f-fixture-provider-not-a-real-model'
spec=importlib.util.spec_from_file_location('installed_helper',ROOT/'scripts/verify-local-analysis.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


class FixtureProvider(BaseHTTPRequestHandler):
    calls=0
    def log_message(self,*args):pass
    def do_POST(self):
        length=int(self.headers.get('Content-Length','0'))
        if not 0<length<=2_000_000:self.send_error(400);return
        body=json.loads(self.rfile.read(length))
        if self.path=='/api/show':result={'capabilities':['completion','vision'],'model_info':{'fixture':True}}
        elif self.path=='/api/chat':
            if body.get('model')!=MODEL:self.send_error(400);return
            FixtureProvider.calls+=1
            result={'model':MODEL,'message':{'content':json.dumps({'description':'Deterministic fixture response; no real inference','tags':['fixture'],'suggestions':{'primary':'A01','roles':['role.item'],'styles':['style.pixel']}})}}
        else:self.send_error(404);return
        raw=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)


def fixtures(source):
    Image.new('RGBA',(32,16),(255,0,0,0)).save(source/'image.png')
    Image.new('RGB',(16,32),'blue').save(source/'image.jpg')
    Image.new('RGB',(8,8),'red').save(source/'animation.gif',save_all=True,append_images=[Image.new('RGB',(8,8),'blue')],duration=[100,200],loop=0)
    Image.new('RGBA',(8,8),'red').save(source/'animation.png',save_all=True,append_images=[Image.new('RGBA',(8,8),'blue')],duration=[100,200],loop=0)
    with wave.open(str(source/'audio.wav'),'wb') as output:output.setparams((1,2,8000,8000,'NONE','PCM'));output.writeframes(b'\0'*16000)
    (source/'shape.obj').write_text('mtllib ../not-opened.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n',encoding='utf-8')
    binary=struct.pack('<9f',0,0,0,1,0,0,0,1,0)
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':36,'uri':'data:application/octet-stream;base64,'+base64.b64encode(binary).decode()}],
        'bufferViews':[{'buffer':0,'byteLength':36}],'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3'}],
        'meshes':[{'primitives':[{'attributes':{'POSITION':0}}]}]}
    (source/'shape.gltf').write_text(json.dumps(doc),encoding='utf-8')
    del doc['buffers'][0]['uri'];data=json.dumps(doc).encode();data+=b' '*((-len(data))%4)
    (source/'shape.glb').write_bytes(struct.pack('<4sII',b'glTF',2,28+len(data)+len(binary))+struct.pack('<II',len(data),0x4E4F534A)+data+struct.pack('<II',len(binary),0x004E4942)+binary)
    (source/'code.py').write_text('import os\ndef example():\n    return 42\n',encoding='utf-8')
    (source/'data.json').write_text('{"items":[1,2]}',encoding='utf-8')
    (source/'data.csv').write_text('name,value\nfixture,=DO_NOT_EXECUTE()\n',encoding='utf-8')
    for ext in ('unity','prefab','vfx','mat'):(source/f'declaration.{ext}').write_text('%YAML 1.1\n--- !u!1 &1\nref: {guid: 0123456789abcdef0123456789abcdef}\n',encoding='utf-8')
    with zipfile.ZipFile(source/'package.zip','w') as output:output.writestr('../never-extract.py',b'raise RuntimeError()')
    head=bytearray(54);struct.pack_into('>I',head,12,0x5F0F3CF5);struct.pack_into('>H',head,18,1024)
    (source/'font.ttf').write_bytes(b'\0\1\0\0'+struct.pack('>4H',2,0,0,0)+struct.pack('>4sIII',b'head',0,44,54)+struct.pack('>4sIII',b'maxp',0,98,6)+head+struct.pack('>IH',0x10000,12))
    def box(kind,data):return struct.pack('>I4s',len(data)+8,kind)+data
    (source/'video.mp4').write_bytes(box(b'ftyp',b'isom\0\0\0\0isom')+box(b'moov',box(b'mvhd',b'\0'*12+struct.pack('>II',1000,2500))+box(b'trak',b'')))
    (source/'unsupported.fbx').write_bytes(b'not a supported parser')
    (source/'broken.wav').write_bytes(b'not WAV')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core',required=True);parser.add_argument('--report',required=True);args=parser.parse_args()
    # Refuse to replace an existing listener/model runtime.
    server=ThreadingHTTPServer(('127.0.0.1',11434),FixtureProvider)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    root=ROOT/'.artifacts'/('m08f-installed-'+str(uuid4()));source=root/'source';source.mkdir(parents=True);fixtures(source)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    core=None
    try:
        core=helper.InstalledCore(args.core,root/'data');call=core.call
        library=call('library.register',{'path':str(source)})['library']['id'];call('library.scan',{'library_id':library})
        assets={};cursor=None
        while True:
            page=call('asset.list',{'after_id':cursor})
            assets.update({Path(a['path']).name:a['id'] for a in page['items']})
            cursor=page['next_cursor']
            if cursor is None:break
        assert len(assets)==len(hashes) and call('analysis.jobs')['items']==[] and FixtureProvider.calls==0
        observations={}
        for name in hashes:
            asset=assets[name]
            if name in ('unsupported.fbx','broken.wav'):continue
            observations[name]=call('asset.technical.collect',{'asset_id':asset,'confirmed':True})
        for name in ('unsupported.fbx','broken.wav'):
            try:call('asset.technical.collect',{'asset_id':assets[name],'confirmed':True})
            except RuntimeError as error:assert str(error)=='UNSUPPORTED_FORMAT'
            else:raise AssertionError('UNSUPPORTED_REPORTED_SUCCESS')
        assert call('analysis.jobs')['items']==[] and FixtureProvider.calls==0
        model=call('model.register',{'provider_name':'Ollama','kind':'local','model_id':MODEL,'modalities':['image','text']})['id']
        call('model.inspect',{'id':model});call('model.policy',{'id':model,'enabled':True,'allow_external':False,'allow_paid':False,'budget_usd':'0','max_requests':50})
        results={};statuses={}
        for name,kind in (('image.png','image'),('image.jpg','image'),('shape.obj','threeD'),('shape.gltf','threeD'),('shape.glb','threeD'),('animation.gif','animation'),('animation.png','animation'),('code.py','text'),('data.json','text'),('declaration.vfx','text')):
            asset=assets[name];plan={'mode':'selected','scope':'all','library_id':None,'folder_parts':[],'selected_ids':[asset],'model_id':model,'input_kind':kind}
            before=FixtureProvider.calls;preview=call('analysis.preview',plan)
            assert before==FixtureProvider.calls and preview['eligibleCount']==1
            job=call('analysis.start',{'plan':plan,'plan_token':preview['planToken'],'request_id':str(uuid4()),'confirmed':True,'confirm_external':False,'confirm_paid':False})['jobId']
            deadline=time.monotonic()+10
            while True:
                status=call('analysis.status',{'job_id':job})
                if status['status'] not in ('queued','running'):break
                if time.monotonic()>deadline:raise RuntimeError('FIXTURE_WORKER_TIMEOUT')
                time.sleep(.05)
            assert status['succeeded']==1 and status['failed']==0,status
            result=call('asset.analysis',{'asset_id':asset})['active'];assert result and result['features']['schema']=='asset-description.v4'
            results[name]=result;statuses[name]=status['status']
        params={'asset_id':assets['image.png'],'result_id':results['image.png']['id']}
        preview=call('analysis.review',params)
        classification=call('analysis.review.apply',{**params,'plan_token':preview['planToken'],'expected_revision':preview['expectedRevision'],'confirmed':True})
        assert classification['source']=='user' and classification['value']['primary']=='A01'
        calls=FixtureProvider.calls;core.close();core=helper.InstalledCore(args.core,root/'data');call=core.call
        for name,result in results.items():assert call('asset.analysis',{'asset_id':assets[name]})['active']==result
        for name,result in observations.items():assert call('asset.technical',{'asset_id':assets[name]})==result
        assert call('catalog.classification',{'asset_id':assets['image.png']})==classification
        assert FixtureProvider.calls==calls and len(call('analysis.jobs')['items'])==len(results)
        assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}==hashes
        report={'passed':True,'parserObservations':len(observations),'analysisPaths':statuses,'restartPreserved':True,'sourceUnchanged':True,
            'guiOpened':False,'externalCalls':0,'realModelInference':False,'provider':'deterministic loopback fixture; not a real model',
            'fixtureInferenceCalls':FixtureProvider.calls,'audioExternalAdapter':'unit mock only; no real provider validation',
            'sidecarSha256':hashlib.sha256(Path(args.core).read_bytes()).hexdigest()}
        Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
    finally:
        if core:core.close()
        server.shutdown();server.server_close();thread.join(5)


if __name__=='__main__':main()
