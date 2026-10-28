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


def inspect_external(model_id, key=None):
    from decimal import Decimal
    data=metadata('https://openrouter.ai/api/v1/models',key=key)
    models=data.get('data')
    if not isinstance(models,list): raise ValueError()
    row=next((r for r in models if isinstance(r,dict) and r.get('id')==model_id),None)
    if row is None:return {'status':'model_not_found','modalities':[]}
    pricing=row.get('pricing')
    if not isinstance(pricing,dict) or len(pricing)>16 or not {'prompt','completion'}<=set(pricing):raise ValueError()
    prices={}
    for name,value in pricing.items():
        if not isinstance(name,str) or not isinstance(value,str) or len(name)>80 or len(value)>80:raise ValueError()
        amount=Decimal(value)
        if not amount.is_finite() or amount<0:raise ValueError()
        prices[name]=str(amount)
    modalities=row.get('architecture',{}).get('input_modalities')
    if not isinstance(modalities,list) or not all(isinstance(m,str) for m in modalities):raise ValueError()
    return {'status':'available','modalities':[m for m in modalities if m in ('text','image','audio')],
            'pricing':prices,'costClass':'free' if all(Decimal(p)==0 for p in prices.values()) else 'paid',
            'authentication':'credential_sent' if key else 'not_tested'}
