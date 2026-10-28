"""Metadata requests only; no inference, downloads, redirects or environment proxies."""
import json
import time
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def metadata(url, payload=None, key=None):
    headers={'Accept':'application/json','Content-Type':'application/json'}
    if key: headers['Authorization']='Bearer '+key
    request=Request(url,data=json.dumps(payload).encode('utf-8') if payload is not None else None,headers=headers)
    deadline=time.monotonic()+1.5
    with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=0.5) as response:
        chunks=[];size=0
        while True:
            if time.monotonic()>deadline: raise TimeoutError()
            chunk=response.read1(65536)
            if not chunk: break
            size+=len(chunk)
            if size>2_000_000: raise ValueError()
            chunks.append(chunk)
        result=json.loads(b''.join(chunks))
        if not isinstance(result,dict): raise ValueError()
        return result


def inspect_local(model_id):
    if model_id.endswith(':cloud'): return {'status':'cloud_not_local','modalities':[]}
    data=metadata('http://127.0.0.1:11434/api/show',{'model':model_id})
    if data.get('remote_host') or data.get('remote_model'): return {'status':'cloud_not_local','modalities':[]}
    caps=data.get('capabilities')
    if not isinstance(caps,list) or not all(isinstance(c,str) for c in caps): raise ValueError()
    modalities=[]
    if 'completion' in caps: modalities.append('text')
    if 'vision' in caps: modalities.append('image')
    if 'audio' in caps: modalities.append('audio')
    return {'status':'available','modalities':modalities}
