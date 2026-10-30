import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

if (process.platform !== 'win32' || process.arch !== 'x64') throw new Error('This package target requires Windows x64.');
const root = fileURLToPath(new URL('../', import.meta.url));
const artifacts = join(root, '.artifacts');
const venv = join(artifacts, 'core-build-venv');
const python = join(venv, 'Scripts', 'python.exe');
function run(program, args) {
  const result = spawnSync(program, args, { cwd: root, stdio: 'inherit', windowsHide: true,
    timeout: 300_000, env: { ...process.env, PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1' } });
  if (result.error || result.status !== 0) throw new Error('Core packaging failed. See the build output.');
}
mkdirSync(artifacts, { recursive: true });
if (!existsSync(python)) run(process.env.AI_ASSET_HUB_PYTHON || 'python', ['-m', 'venv', venv]);
run(python, ['-m', 'pip', 'install', '--disable-pip-version-check', '-r', join(root, 'python-core', 'requirements-build.txt')]);
const binaries = join(root, 'src-tauri', 'binaries');
run(python, ['-m', 'PyInstaller', '--noconfirm', '--onedir', '--console', '--noupx',
  '--name', 'ai-asset-hub-core', '--distpath', join(binaries, 'core'),
  '--workpath', join(artifacts, 'pyinstaller-work'), '--specpath', artifacts,
  '--paths', join(root, 'python-core'), '--add-data', `${join(root, 'db', 'migrations')}:migrations`,
  '--hidden-import', 'ai_asset_hub_core.collections',
  '--hidden-import', 'ai_asset_hub_core.packages',
  '--hidden-import', 'ai_asset_hub_core.metadata_store',
  '--hidden-import', 'ai_asset_hub_core.asset_management',
  '--hidden-import', 'ai_asset_hub_core.asset_composition',
  join(root, 'python-core', 'desktop_entry.py')]);
const packagedModules = readFileSync(join(artifacts, 'pyinstaller-work', 'ai-asset-hub-core', 'PYZ-00.toc'), 'utf8');
for (const module of ['metadata_store', 'metadata_values', 'classification_axes', 'taxonomy', 'asset_composition', 'asset_management', 'collections', 'packages', 'creators', 'provenance', 'source_records', 'license_records', 'provenance_policy']) {
  if (!packagedModules.includes(`'ai_asset_hub_core.${module}'`)) throw new Error(`Core contract module missing from bundle: ${module}`);
}
const source = join(binaries, 'core', 'ai-asset-hub-core', 'ai-asset-hub-core.exe');
const target = join(binaries, 'ai-asset-hub-core-x86_64-pc-windows-msvc.exe');
copyFileSync(source, target);
writeFileSync(join(artifacts, 'core-build-manifest.json'), JSON.stringify({
  target: 'x86_64-pc-windows-msvc', pyinstaller: '6.22.3',
  sha256: createHash('sha256').update(readFileSync(target)).digest('hex'),
}, null, 2) + '\n');
