import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../python-core/", import.meta.url));
const tests = fileURLToPath(new URL("../python-core/tests/", import.meta.url));
const python = process.env.AI_ASSET_HUB_PYTHON || "python";
const result = spawnSync(python, ["-B", "-m", "unittest", "discover", "-s", tests, "-v"], {
  cwd: root, encoding: "utf8", timeout: 30_000, windowsHide: true,
  env: { ...process.env, PYTHONUTF8: "1", PYTHONDONTWRITEBYTECODE: "1" },
});
if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);
if (result.error) {
  console.error("Core tests could not run. Set AI_ASSET_HUB_PYTHON to a Python 3.11+ executable.");
}
process.exitCode = result.error ? 1 : result.status ?? 1;
