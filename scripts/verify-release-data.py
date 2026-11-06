"""Owned previous-installation data fixture; checks actual updates/uninstall retention."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_data_helper',ROOT/'scripts/verify-local-analysis.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['seed','check','retained'],required=True);parser.add_argument('--core');parser.add_argument('--data',required=True);parser.add_argument('--state',required=True);parser.add_argument('--source');args=parser.parse_args()
    data=Path(args.data);state_path=Path(args.state);core=None
    try:
        if args.mode=='seed':
            source=Path(args.source);source.mkdir(parents=True);path=source/'이전 설치 원본.txt';path.write_bytes(b'owned source, never modify')
            core=helper.InstalledCore(args.core,data);call=core.call
            library=call('library.register',dict(path=str(source)))['library']['id'];call('library.scan',dict(library_id=library));asset=call('asset.list',{})['items'][0]['id']
            call('asset.tags',dict(asset_id=asset,add=['이전 태그','keep'],remove=[]));call('asset.annotate',dict(asset_id=asset,title='이전 설치 이름',description='이전 설치 사용자 설명'))
            expected=call('asset.annotations',dict(asset_id=asset));core.close();core=None
            state=dict(libraryId=library,assetId=asset,annotations=expected,sourcePath=str(path),sourceSha256=sha(path),dbSha256=sha(data/'asset_hub.sqlite'))
            state_path.write_text(json.dumps(state,ensure_ascii=True),encoding='utf-8')
        else:
            state=json.loads(state_path.read_text());assert sha(Path(state['sourcePath']))==state['sourceSha256'];assert sha(data/'asset_hub.sqlite')==state['dbSha256']
            if args.mode=='check':
                core=helper.InstalledCore(args.core,data);assert core.call('asset.annotations',dict(asset_id=state['assetId']))==state['annotations']
                assert core.call('library.list',{})['libraries'][0]['id']==state['libraryId'];core.close();core=None
            else:
                connection=sqlite3.connect((data/'asset_hub.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
                try:assert connection.execute('SELECT count(*) FROM assets WHERE id=?',(state['assetId'],)).fetchone()[0]==1
                finally:connection.close()
        print(json.dumps(dict(passed=True,mode=args.mode,dbAndAnnotationsPreserved=True,originalSourcePreserved=True,guiOpened=False)))
    finally:
        if core:core.close()


if __name__=='__main__':main()
