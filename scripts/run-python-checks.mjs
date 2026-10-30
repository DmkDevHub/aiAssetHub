import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { existsSync } from 'node:fs';

const root = fileURLToPath(new URL("../python-core/", import.meta.url));
const tests = fileURLToPath(new URL("../python-core/tests/", import.meta.url));
const bundled = fileURLToPath(new URL('../.artifacts/core-build-venv/Scripts/python.exe', import.meta.url));
const python = process.env.AI_ASSET_HUB_PYTHON || 'python';
const packages = fileURLToPath(new URL('../.artifacts/core-build-venv/Lib/site-packages', import.meta.url));
const bootstrap = `import site,sys,runpy;${existsSync(bundled) ? `site.addsitedir(${JSON.stringify(packages)});` : ''}sys.argv=['unittest',*sys.argv[1:]];runpy.run_module('unittest',run_name='__main__')`;
const result = spawnSync(python, ["-B", "-c", bootstrap, "discover", "-s", tests, "-v"], {
  cwd: root, encoding: "utf8", timeout: 60_000, windowsHide: true,
  env: { ...process.env, PYTHONUTF8: "1", PYTHONDONTWRITEBYTECODE: "1", ...(existsSync(bundled) ? {PYTHONPATH:fileURLToPath(new URL('../.artifacts/core-build-venv/Lib/site-packages',import.meta.url))} : {}) },
});
if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);
if (result.error) {
  console.error(result.error.code==='ETIMEDOUT' ? 'Core tests exceeded the 60-second deadline.' : "Core tests could not run. Set AI_ASSET_HUB_PYTHON to a Python 3.11+ executable.");
}
process.exitCode = result.error ? 1 : result.status ?? 1;
