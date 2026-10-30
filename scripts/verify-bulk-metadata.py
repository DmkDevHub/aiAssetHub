"""Installed metadata exchange/hash verification using owned fixtures. No models or GUI."""
import argparse
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installed_helper',ROOT/'scripts/verify-local-analysis.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core',required=True);parser.add_argument('--report',required=True);args=parser.parse_args()
    root=ROOT/'.artifacts'/('m08g-installed-'+str(uuid4()));source=root/'source';source.mkdir(parents=True)
    for name,data in (('한글.bin',b'owned identical fixture'),('copy.bin',b'owned identical fixture'),('different.bin',b'different fixture')):(source/name).write_bytes(data)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()};core=None
    try:
        core=helper.InstalledCore(args.core,root/'data');call=core.call
        library=call('library.register',{'path':str(source)})['library']['id'];call('library.scan',{'library_id':library})
        assets={};cursor=None
        while True:
            page=call('asset.list',{'after_id':cursor});assets.update({Path(a['path']).name:a['id'] for a in page['items']});cursor=page['next_cursor']
            if cursor is None:break
        ids=sorted([assets['한글.bin'],assets['copy.bin']]);subject={'kind':'asset','id':ids[0]}
        initial_jobs=call('analysis.jobs');initial_embeddings=call('embedding.status')
        group=call('asset.groups.create',{'value':{'name':'테스트 그룹','description':''}})
        creator=call('creator.create',{'value':dict(name='fixture company',kind='company',brand='',homepageUrl='',profileUrl='',contact='PRIVATE-CONTACT',country='',description='')})
        source_record=call('source.create',{'subject':subject,'value':{'site':'private-source-public-name','productName':'product','originalUrl':'https://example.com/?key=PRIVATE-URL','productUrl':'','downloadUrl':'','purchase':{'amount':'12345','currency':'USD','purchasedOn':'','downloadedOn':''}}})
        request={'asset_ids':ids,'changes':{'groups':{'add':[group['id']],'remove':[]},'classification':{'primary':'A01'},'tags':{'add':['한글 태그'],'remove':[]},'creators':{'add':[{'creator_id':creator['id'],'role':'creator'}],'remove':[]},'sources':{'append':[{'site':'public shop','productName':'public product'}]}}}
        cursor=None;token=None;reviewed=[]
        while True:
            preview=call('bulk.preview',{'request':request,'after_id':cursor,'plan_token':token});token=preview['planToken'];reviewed.extend(t['assetId'] for t in preview['items']);cursor=preview['next_cursor']
            if cursor is None:break
        assert reviewed==ids and call('asset.annotations',{'asset_id':ids[0]})['tags']==[]
        try:call('bulk.apply',{'request':request,'plan_token':token,'confirmed':False})
        except RuntimeError as error:assert str(error)=='INVALID_PARAMS'
        else:raise AssertionError('UNAPPROVED_BULK_SUCCEEDED')
        assert call('bulk.apply',{'request':request,'plan_token':token,'confirmed':True})['updated']==2
        fields=['basic','tags','classification','groups','packages','creators','sources','relations']
        exported=call('exchange.export',{'asset_ids':ids,'fields':fields,'format':'json'})
        assert exported['privateFieldsExcluded'] and not any(v in exported['content'] for v in ('PRIVATE-','12345',str(source)))
        csv_export=call('exchange.export',{'asset_ids':ids,'fields':['basic','tags'],'format':'csv'})
        for row in csv.DictReader(io.StringIO(csv_export['content'])):
            assert not any(cell.lstrip().startswith(('=','+','-','@','\t','\r')) for cell in row.values())
        csv_preview=call('exchange.preview',{'content':csv_export['content'],'format':'csv','use_current_versions':False,'after_id':None,'plan_token':None});assert csv_preview['changedCount']==0
        document=json.loads(exported['content'])
        for index,row in enumerate(document['assets']):row['values']['basic']['title']='=fixture-formula-'+str(index)
        target=next(r for r in document['assets'] if r['asset_id']==ids[0]);next(r for r in target['values']['sources'] if r['id']==source_record['id'])['site']='changed-public-site'
        content=json.dumps(document,ensure_ascii=False,separators=(',',':'));params={'content':content,'format':'json','use_current_versions':False}
        preview=call('exchange.preview',{**params,'after_id':None,'plan_token':None});assert preview['conflictCount']==0
        assert call('asset.annotations',{'asset_id':ids[0]})['title']==''
        applied=call('exchange.apply',{**params,'plan_token':preview['planToken'],'confirmed':True});assert applied['updated']==2
        private=call('source.get',{'record_id':source_record['id'],'include_private':True,'confirmed':True})
        assert private['value']['site']=='changed-public-site' and private['value']['originalUrl']=='https://example.com/?key=PRIVATE-URL' and private['value']['purchase']['amount']=='12345'
        stale=call('exchange.preview',{**params,'after_id':None,'plan_token':None});assert stale['conflictCount']>0
        try:call('exchange.apply',{**params,'plan_token':stale['planToken'],'confirmed':True})
        except RuntimeError as error:assert str(error)=='METADATA_CONFLICT'
        else:raise AssertionError('STALE_IMPORT_SUCCEEDED')
        job=call('duplicates.start',{'asset_ids':ids,'confirmed':True})['jobId'];deadline=time.monotonic()+10
        while True:
            status=call('duplicates.status',{'job_id':job,'after_id':None})
            if status['status'] not in ('queued','running'):break
            if time.monotonic()>deadline:raise RuntimeError('HASH_TIMEOUT')
            time.sleep(.05)
        assert status['hashed']==2 and status['failed']==0
        candidates=call('duplicates.candidates',{'job_id':job,'after_hash':None,'after_file_id':None})
        assert len(candidates['items'])==1 and candidates['items'][0]['fileCount']==2
        assert candidates['items'][0]['rightsEquivalence']=='not-determined' and candidates['automaticDelete'] is False
        saved={asset:call('asset.annotations',{'asset_id':asset}) for asset in ids}
        assert call('analysis.jobs')==initial_jobs and call('embedding.status')==initial_embeddings
        core.close();core=helper.InstalledCore(args.core,root/'data');call=core.call
        assert {asset:call('asset.annotations',{'asset_id':asset}) for asset in ids}==saved
        assert call('duplicates.candidates',{'job_id':job,'after_hash':None,'after_file_id':None})==candidates
        assert call('duplicates.status',{'job_id':job,'after_id':None})['needsRecovery'] is False
        assert call('duplicates.list',{})['items'][0]['id']==job
        assert call('analysis.jobs')==initial_jobs and call('embedding.status')==initial_embeddings
        assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}==hashes
        report={'passed':True,'bulkTargets':2,'jsonFields':fields,'csvRoundtrip':True,'staleImportRejected':True,'privateFieldsExcluded':True,
            'privateSourcePreserved':True,'hashFiles':2,'duplicateGroups':1,'rightsEquivalence':'not-determined','restartPreserved':True,
            'sourceUnchanged':True,'analysisOrEmbeddingCreated':False,'guiOpened':False,'modelCalls':0,'externalCalls':0,
            'sidecarSha256':hashlib.sha256(Path(args.core).read_bytes()).hexdigest()}
        Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
    finally:
        if core:core.close()


if __name__=='__main__':main()
