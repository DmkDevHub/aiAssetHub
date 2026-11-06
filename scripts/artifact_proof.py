"""Bind installation evidence to exact build inputs, payloads and distributable files."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORTS={
    'mcp':'m08-installed-host.json','unity':'m09-installed-unity-host.json',
    'multiformat':'m08f-installed-multiformat.json','bulk':'m08g-installed-metadata.json',
    'smart':'m08i-installed-discovery.json','upgrade':'m10-upgrade-result.json',
    'release':'m10-installed-acceptance.json',
}
LOGS=('m10-check.txt','m10-rust-tests.txt')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root,folder):
    return {p.relative_to(root).as_posix():sha(p) for p in sorted((root/folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def sources(root):
    result={}
    for folder in ('python-core/ai_asset_hub_core','src','src-tauri/src','src-tauri/capabilities','unity-package','db/migrations','scripts'):
        for p in sorted((root/folder).rglob('*')):
            if p.is_file() and p.suffix in ('.py','.ts','.vue','.css','.rs','.cs','.sql','.asmdef','.json','.meta','.mjs','.ps1','.nsh'):
                result[p.relative_to(root).as_posix()]=sha(p)
    for name in ('package.json','package-lock.json','index.html','vite.config.ts','tsconfig.json','tsconfig.node.json','src-tauri/build.rs','src-tauri/icons/icon.ico','src-tauri/Cargo.toml','src-tauri/Cargo.lock','src-tauri/tauri.conf.json','python-core/desktop_entry.py','python-core/requirements-build.txt','python-core/requirements-runtime.txt'):
        p=root/name
        if p.is_file():result[name]=sha(p)
    return dict(sorted(result.items()))


def fingerprint(root):
    return dict(sourceSha256=sources(root),payloadSha256=tree(root,'src-tauri/binaries/core/ai-asset-hub-core'),frontendSha256=tree(root,'dist'))


def snapshot(root):
    value=fingerprint(root);build=json.loads((root/'.artifacts/core-build-manifest.json').read_text(encoding='utf-8'))
    for key in ('sourceSha256','payloadSha256','frontendSha256'):
        if not value[key] or build.get(key)!=value[key]:raise ValueError('BUILD_INPUTS_CHANGED')
    files=('src-tauri/target/release/bundle/nsis/AI Asset Hub_0.5.0_x64-setup.exe','src-tauri/target/release/ai-asset-hub.exe','src-tauri/binaries/ai-asset-hub-core-x86_64-pc-windows-msvc.exe')
    value['binaries']={name:dict(sizeBytes=(root/name).stat().st_size,sha256=sha(root/name)) for name in files}
    if build.get('sha256')!=value['binaries'][files[2]]['sha256']:raise ValueError('CORE_BINARY_CHANGED')
    return value


def verify(root,proof,require_all=True):
    if proof.get('passed') is not True or proof.get('schema')!='installer-evidence.v1':raise ValueError('INSTALLER_NOT_VERIFIED')
    if require_all and set(proof.get('checks',[]))!=set(REPORTS):raise ValueError('INSTALLER_CHECKS_MISSING')
    if proof.get('snapshot')!=snapshot(root):raise ValueError('VERIFIED_ARTIFACT_CHANGED')
    expected={REPORTS[name] for name in proof['checks']}|set(LOGS)
    if set(proof.get('reports',{}))!=expected:raise ValueError('REPORTS_MISSING')
    for name,digest in proof['reports'].items():
        if sha(root/'.artifacts'/name)!=digest:raise ValueError('VERIFIED_REPORT_CHANGED')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['sources','build','begin','finish'],required=True);parser.add_argument('--checks',default='');args=parser.parse_args()
    folder=ROOT/'.artifacts';pending=folder/'installer-verification-pending.json';finished=folder/'installer-verification.json'
    if args.phase=='sources':print(json.dumps(sources(ROOT)));return
    if args.phase=='build':print(json.dumps(fingerprint(ROOT)));return
    if args.phase=='begin':
        checks=sorted(set(filter(None,args.checks.split(','))))
        if set(checks)-set(REPORTS):raise ValueError('INVALID_CHECKS')
        value=dict(schema='installer-evidence.v1',checks=checks,snapshot=snapshot(ROOT),startedAt=datetime.now(timezone.utc).isoformat())
        finished.unlink(missing_ok=True) # Only our generated evidence, never application/user data.
        pending.write_text(json.dumps(value,indent=2),encoding='utf-8');print('{"started":true}');return
    value=json.loads(pending.read_text(encoding='utf-8'))
    if value['snapshot']!=snapshot(ROOT):raise ValueError('ARTIFACT_CHANGED_DURING_TEST')
    value.update(passed=True,finishedAt=datetime.now(timezone.utc).isoformat(),reports={name:sha(folder/name) for name in sorted({REPORTS[k] for k in value['checks']}|set(LOGS))})
    verify(ROOT,value,require_all=False)
    finished.write_text(json.dumps(value,indent=2),encoding='utf-8');pending.unlink();print('{"passed":true,"artifactsBound":true}')


if __name__=='__main__':main()
