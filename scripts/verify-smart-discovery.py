"""Installed smart groups/recommendations with owned fixtures, no inference or GUI."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installed_helper',ROOT/'scripts/verify-local-analysis.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core',required=True);parser.add_argument('--report',required=True);args=parser.parse_args()
    root=ROOT/'.artifacts'/('m08i-installed-'+str(uuid4()));source=root/'source';source.mkdir(parents=True)
    for name in ('source.bin','target.bin','unrelated.bin'):(source/name).write_bytes(('owned '+name).encode())
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()};core=None
    try:
        core=helper.InstalledCore(args.core,root/'data');call=core.call
        library=call('library.register',dict(path=str(source)))['library']['id'];call('library.scan',dict(library_id=library))
        assets={};cursor=None
        while True:
            page=call('asset.list',dict(after_id=cursor));assets.update({Path(a['path']).name:a['id'] for a in page['items']});cursor=page['next_cursor']
            if cursor is None:break
        origin,target=assets['source.bin'],assets['target.bin']
        for asset in (origin,target):call('asset.tags',dict(asset_id=asset,add=['공유'],remove=[]))
        jobs=call('analysis.jobs');embeddings=call('embedding.status')
        saved=call('catalog.smart.save',dict(group_id=None,name='설치 스마트 그룹',description='',definition=dict(schema='smart-group.v1',query='',criteria=dict(tag='공유'),include_groups=[]),expected_revision=0))
        request=dict(group_id=saved['id'],query='',criteria={},sort='source',after_id=None)
        assert call('catalog.smart.evaluate',request)['ids']==sorted([origin,target])
        call('asset.tags',dict(asset_id=target,add=[],remove=['공유']))
        assert call('catalog.smart.evaluate',request)['ids']==[origin]
        call('asset.tags',dict(asset_id=target,add=['공유'],remove=[]))
        candidates=call('catalog.related',dict(asset_id=origin,mode='hybrid',criteria={},limit=10))
        assert [r['id'] for r in candidates['items']]==[target]
        assert candidates['vectorStatus']=='source-vector-unavailable' and not candidates['inferenceCalled'] and not candidates['relationshipCreated']
        assert call('asset.relations',dict(asset_id=origin))['value']==[]
        links=[dict(targetId=target,kind='related')]
        call('asset.relations.save',dict(asset_id=origin,value=links,expected_revision=0))
        assert call('catalog.related',dict(asset_id=origin,mode='metadata',criteria={},limit=10))['items']==[]
        try:call('asset.relations.save',dict(asset_id=origin,value=[],expected_revision=0))
        except RuntimeError as error:assert str(error)=='METADATA_CONFLICT'
        else:raise AssertionError('STALE_RELATION_NOT_REJECTED')
        assert call('analysis.jobs')==jobs and call('embedding.status')==embeddings
        core.close();core=None;core=helper.InstalledCore(args.core,root/'data');call=core.call
        assert call('catalog.smart.get',dict(group_id=saved['id']))==saved
        assert call('catalog.smart.evaluate',request)['ids']==sorted([origin,target])
        assert call('asset.relations',dict(asset_id=origin))['value']==links
        assert call('analysis.jobs')==jobs and call('embedding.status')==embeddings
        assert all(hashlib.sha256((source/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())
        report=dict(passed=True,smartDynamicResults=True,smartRestartPreserved=True,recommendationSeparatedFromConfirmation=True,
            staleRelationRejected=True,relationRestartPreserved=True,sourceUnchanged=True,inferenceCalls=0,guiOpened=False,
            semanticVectors='unit mathematical fixture; installed test verifies unavailable state without generation',sidecarSha256=hashlib.sha256(Path(args.core).read_bytes()).hexdigest())
        Path(args.report).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
    finally:
        if core:core.close()


if __name__=='__main__':main()
