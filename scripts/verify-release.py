"""Installed v0.5 acceptance: real background scan, responsive IPC and offline restore.
All data is owned synthetic fixtures. No model/provider request or GUI automation.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_helper',ROOT/'scripts/verify-local-analysis.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--core',required=True);parser.add_argument('--report',required=True);parser.add_argument('--count',type=int,default=5000);args=parser.parse_args()
    if not 100<=args.count<=5000:raise ValueError('fixture scope')
    executable=str(Path(args.core).resolve());root=ROOT/'.artifacts'/('m10-installed-'+str(uuid4()));source=root/'한글 원본';source.mkdir(parents=True);data=root/'data'
    hashes={}
    for i in range(args.count):
        directory=source/f'하위_{i//250:02}';directory.mkdir(exist_ok=True);path=directory/f'에셋_{i:05}.txt';path.write_bytes(f'owned fixture {i}'.encode());hashes[path]=sha(path)
    core=None;started=time.monotonic()
    def offline(identifier):
        result=subprocess.run([executable,'--maintenance','restore','--data-dir',str(data),'--environment','production','--backup-id',identifier,'--confirmed'],
            capture_output=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
        assert not result.stderr
        return result.returncode,json.loads(result.stdout)
    try:
        core=helper.InstalledCore(executable,data);call=core.call;library=call('library.register',dict(path=str(source)))['library']['id']
        start=time.perf_counter();job=call('library.scan.start',dict(library_id=library));start_ms=(time.perf_counter()-start)*1000
        health_times=[];deadline=time.monotonic()+90
        while True:
            start=time.perf_counter();health=call('health.get');health_times.append((time.perf_counter()-start)*1000);assert health['database']['status']=='ready'
            status=call('library.scan.status',dict(job_id=job['jobId']))
            if status['status']=='completed':break
            assert status['status'] in ('queued','running') and time.monotonic()<deadline,status
            time.sleep(.1)
        assert status['result']['processed']==args.count and start_ms<1500 and max(health_times)<2000
        rows=[];cursor=None;pages=0
        while True:
            page=call('asset.list',dict(after_id=cursor,limit=100));rows.extend(page['items']);pages+=1;cursor=page['next_cursor']
            if cursor is None:break
        assert len(rows)==args.count and len({r['id'] for r in rows})==args.count and pages<args.count/5
        asset=rows[0]['id'];call('asset.tags',dict(asset_id=asset,add=['백업 시점'],remove=[]));expected=call('asset.annotations',dict(asset_id=asset))
        backup=call('maintenance.backup',dict(confirmed=True));assert call('maintenance.list',{})['items'][0]['manifestValid']
        call('asset.tags',dict(asset_id=asset,add=['백업 이후 변경'],remove=[]))
        denied_code,denied=offline(backup['id']);assert denied_code!=0 and denied['error']['code']=='DATA_IN_USE'
        core.close();core=None
        returncode,restored=offline(backup['id']);assert returncode==0 and restored['data']['restored'] and restored['data']['analysisResumed'] is False
        core=helper.InstalledCore(executable,data);call=core.call
        assert call('asset.annotations',dict(asset_id=asset))==expected
        assert call('library.scan.status',dict(job_id=job['jobId']))['status']=='completed'
        assert call('diagnostics.read',dict(kind='analysis'))['items']==[] and call('diagnostics.budget',{})['items']==[]
        assert call('analysis.jobs',{})['items']==[] and call('embedding.status',{})['readyCount']==0
        corrupt=call('maintenance.backup',dict(confirmed=True));core.close();core=None
        path=data/'backups'/(corrupt['id']+'.sqlite');raw=bytearray(path.read_bytes());raw[0]^=1;path.write_bytes(raw)
        before=sha(data/'asset_hub.sqlite');code,rejected=offline(corrupt['id']);assert code!=0 and rejected['error']['code']=='BACKUP_INVALID' and sha(data/'asset_hub.sqlite')==before
        assert all(sha(p)==digest for p,digest in hashes.items())
        report=dict(passed=True,files=args.count,pages=pages,backgroundScanStartMs=round(start_ms,3),maxConcurrentHealthMs=round(max(health_times),3),
            healthSamples=len(health_times),scanResult=status['result'],lockedRestoreRejected=True,offlineRestoreVerified=True,
            corruptBackupRejectedWithoutDbChange=True,backupAnnotationsRestored=True,sourceHashesPreserved=True,inferenceCalls=0,guiOpened=False,
            coreSha256=sha(Path(executable)),elapsedSeconds=round(time.monotonic()-started,3),verifiedAt=datetime.now(timezone.utc).isoformat())
        Path(args.report).write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:
        if core:core.close()


if __name__=='__main__':main()
