import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('release_evidence',ROOT/'scripts/artifact_proof.py')
evidence=importlib.util.module_from_spec(spec);spec.loader.exec_module(evidence)


class ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'.artifacts/evidence-tests';folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder);self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.files=[
            'src/App.vue','dist/app.js','src-tauri/binaries/core/ai-asset-hub-core/_internal/runtime.dll',
            'src-tauri/target/release/ai-asset-hub.exe','src-tauri/binaries/ai-asset-hub-core-x86_64-pc-windows-msvc.exe',
            'src-tauri/target/release/bundle/nsis/AI Asset Hub_0.5.0_x64-setup.exe',
        ]
        for name in self.files:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(('owned unit fixture '+name).encode())
        (self.root/'.artifacts').mkdir()
        for name in (*evidence.REPORTS.values(),*evidence.LOGS):(self.root/'.artifacts'/name).write_text('owned unit evidence')
        build={**evidence.fingerprint(self.root),'sha256':evidence.sha(self.root/self.files[4])}
        (self.root/'.artifacts/core-build-manifest.json').write_text(json.dumps(build))
        self.proof=dict(schema='installer-evidence.v1',passed=True,checks=sorted(evidence.REPORTS),snapshot=evidence.snapshot(self.root),
            reports={name:evidence.sha(self.root/'.artifacts'/name) for name in (*evidence.REPORTS.values(),*evidence.LOGS)})

    def test_verified_artifact_and_source_and_report_swaps_are_rejected(self):
        evidence.verify(self.root,self.proof)
        for name in (*self.files,'.artifacts/m10-check.txt'):
            with self.subTest(file=name):
                path=self.root/name;before=path.read_bytes();path.write_bytes(before+b'changed after verification')
                try:
                    with self.assertRaises(ValueError):evidence.verify(self.root,self.proof)
                finally:path.write_bytes(before)
        evidence.verify(self.root,self.proof)

    def test_partial_failed_or_incomplete_proofs_cannot_claim_release_acceptance(self):
        for change in (dict(passed=False),dict(checks=['mcp']),dict(reports={}),dict(snapshot={})):
            with self.subTest(change=change):
                value=copy.deepcopy(self.proof);value.update(change)
                with self.assertRaises(ValueError):evidence.verify(self.root,value)
