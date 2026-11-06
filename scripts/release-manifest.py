"""Generate local release evidence only when all current installed-artifact checks pass."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import shutil
from artifact_proof import verify

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    artifacts=ROOT/'.artifacts';installer=ROOT/'src-tauri/target/release/bundle/nsis/AI Asset Hub_0.5.0_x64-setup.exe'
    proof_path=artifacts/'installer-verification.json'
    proof=json.loads(proof_path.read_text(encoding='utf-8'));verify(ROOT,proof)
    core=ROOT/'src-tauri/binaries/ai-asset-hub-core-x86_64-pc-windows-msvc.exe';current=sha(core)
    names=('m10-installed-acceptance.json','m10-upgrade-result.json','m09-installed-unity-host.json','m08-installed-host.json','m08f-installed-multiformat.json','m08g-installed-metadata.json','m08i-installed-discovery.json')
    reports={name:json.loads((artifacts/name).read_text(encoding='utf-8-sig')) for name in names}
    for name,value in reports.items():
        if name!='m08-installed-host.json':assert value.get('passed') is True,name
        recorded=value.get('coreSha256') or value.get('sidecarSha256')
        if recorded:assert recorded==current,('stale binary evidence',name)
    assert reports['m09-installed-unity-host.json']['connectorSha256']==sha(ROOT/'unity-package/Editor/Connector.cs')
    assert 'Installed headless Core/SQLite verification passed; original installation preserved.' in (artifacts/'m10-installed-tests.txt').read_text(encoding='utf-8')
    check=(artifacts/'m10-check.txt').read_text(encoding='utf-8');rust=(artifacts/'m10-rust-tests.txt').read_text(encoding='utf-8')
    node=re.search(r'ℹ tests (\d+)',check);python=re.search(r'Ran (\d+) tests in ([0-9.]+)s\s+OK',check);native=re.search(r'test result: ok\. (\d+) passed; 0 failed',rust)
    assert node and python and native and 'ℹ fail 0' in check
    runtime={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for folder in ('python-core/ai_asset_hub_core','src','src-tauri/src','unity-package/Editor','db/migrations') for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.ts','.vue','.css','.rs','.cs','.sql','.asmdef')}
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    binaries={str(path.relative_to(ROOT)).replace('\\','/'):dict(sizeBytes=path.stat().st_size,sha256=sha(path)) for path in (installer,core,ROOT/'src-tauri/target/release/ai-asset-hub.exe')}
    manifest=dict(version=json.loads((ROOT/'package.json').read_text())['version'],status='internal-acceptance-passed',sourceRevision=revision,
        createdAt=datetime.now(timezone.utc).isoformat(),platform='Windows x64',signing='unsigned',tests=dict(node=int(node[1]),core=int(python[1]),rust=int(native[1])),
        binaries=binaries,runtimeSourceSha256=runtime,evidence={**{name:sha(artifacts/name) for name in names},proof_path.name:sha(proof_path)},
        limitations=['GUI/OS visual layout','clean PC/WebView2 bootstrap','code signing/SmartScreen','personal Codex/Claude configuration and LLM','other Unity/OS','manual real-user acceptance','optional data-purge checkbox'])
    (artifacts/'v0.5.0-release.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (artifacts/'v0.5.0-SHA256SUMS.txt').write_text(''.join(f'{value["sha256"]}  {name}\n' for name,value in binaries.items()),encoding='utf-8')
    delivery=artifacts/'release';delivery.mkdir(exist_ok=True)
    target=delivery/'AIAssetHub-0.5.0-Windows-x64-setup.exe'
    if delivery.is_symlink() or target.is_symlink():raise ValueError('UNSAFE_DELIVERY_PATH')
    shutil.copyfile(installer,target)
    if sha(target)!=sha(installer):raise ValueError('DELIVERY_COPY_CHANGED')
    shutil.copyfile(artifacts/'v0.5.0-release.json',delivery/'release.json')
    (delivery/'SHA256SUMS.txt').write_text(f'{sha(target)}  {target.name}\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,sourceRevision=revision,tests=manifest['tests'],installerSha256=binaries[str(installer.relative_to(ROOT)).replace('\\','/')]['sha256'])))


if __name__=='__main__':main()
