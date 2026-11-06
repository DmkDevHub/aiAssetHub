"""Explicit deterministic scale/malformed/Unicode benchmark. No UI, model or user data."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from uuid import uuid4
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'python-core'))
from ai_asset_hub_core.database import Database
from ai_asset_hub_core.libraries import LibraryService
from ai_asset_hub_core.assets import AssetService
from ai_asset_hub_core.search import SearchService
from ai_asset_hub_core.catalog_query import CatalogQuery
from ai_asset_hub_core.thumbnails import thumbnail


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,default=5000);parser.add_argument('--report',required=True);args=parser.parse_args()
    if not 100<=args.count<=10000:raise ValueError('fixture count out of scope')
    root=ROOT/'.artifacts'/('m10-performance-'+str(uuid4()));source=root/'한글 원본';source.mkdir(parents=True)
    hashes={}
    for i in range(args.count):
        folder=source/f'하위폴더_{i//250:02}';folder.mkdir(exist_ok=True);path=folder/f'에셋_한글_{i:05}.txt';raw=f'owned fixture {i}'.encode();path.write_bytes(raw);hashes[path]=hashlib.sha256(raw).hexdigest()
    for suffix in ('png','jpg','wav','glb'):
        path=source/('비정상.'+suffix);path.write_bytes(b'not a valid media file');hashes[path]=hashlib.sha256(path.read_bytes()).hexdigest()
    database=Database(root/'test.sqlite');service=AssetService(database)
    try:
        with patch('socket.create_connection',side_effect=AssertionError('no network')):
            library=LibraryService(database).register(dict(path=str(source)))['library']['id']
            start=time.perf_counter();scan=service.scan(dict(library_id=library));scan_ms=(time.perf_counter()-start)*1000
            assert scan['complete'] and scan['processed']==args.count+4
            start=time.perf_counter();items=[];cursor=None;pages=0;largest=0
            while True:
                page=service.list(dict(after_id=cursor,limit=100));pages+=1;largest=max(largest,len(json.dumps(page,ensure_ascii=True).encode()))
                assert largest<12000 and page['items'];items.extend(page['items']);cursor=page['next_cursor']
                if cursor is None:break
            list_ms=(time.perf_counter()-start)*1000
            assert len(items)==args.count+4 and len({r['id'] for r in items})==len(items) and pages<args.count/5
            timings=[]
            for query in ('한글','00001','에셋','비정상','zz-no-match')*2:
                start=time.perf_counter();page=SearchService(database).search(dict(query=query));timings.append((time.perf_counter()-start)*1000)
                if query=='00001':assert len(page['ids'])==1
            start=time.perf_counter();filtered=CatalogQuery(database).query(dict(query='한글',criteria=dict(kind='TXT'),sort='size_desc',after_id=None));compound_ms=(time.perf_counter()-start)*1000
            assert len(filtered['ids'])==200
            for item in items:
                if item['kind'] in ('PNG','JPG'):assert thumbnail(database,dict(asset_id=item['id']))['status']=='unavailable'
            start=time.perf_counter();rescan=service.scan(dict(library_id=library));rescan_ms=(time.perf_counter()-start)*1000
            assert rescan['new']==rescan['changed']==rescan['missing']==0
            assert all(hashlib.sha256(p.read_bytes()).hexdigest()==value for p,value in hashes.items())
            assert database.connection.execute('SELECT count(*) FROM analysis_jobs').fetchone()[0]==0
            assert database.connection.execute('SELECT count(*) FROM asset_embeddings').fetchone()[0]==0
        report=dict(passed=True,files=len(items),pages=pages,largestPageBytes=largest,scanMs=round(scan_ms,3),listMs=round(list_ms,3),rescanMs=round(rescan_ms,3),
            searchMedianMs=round(statistics.median(timings),3),searchMaxMs=round(max(timings),3),compoundMs=round(compound_ms,3),sourceHashesPreserved=True,inferenceCalls=0,guiOpened=False)
        # Regression envelopes for this owned benchmark, not a cross-hardware SLA.
        assert scan_ms<30000 and rescan_ms<30000 and list_ms<15000 and max(timings)<2000 and compound_ms<2500,report
        Path(args.report).write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:database.close()


if __name__=='__main__':main()
