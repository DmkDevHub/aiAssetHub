import { readFile } from "node:fs/promises";
import { createServer } from "node:net";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export function checkDevPort(url) {
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once("error", reject);
    probe.listen({ host: url.hostname, port: Number(url.port), exclusive: true }, () => {
      probe.close((error) => error ? reject(error) : resolve());
    });
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const config = JSON.parse(
    await readFile(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8"),
  );
  const url = new URL(config.build.devUrl);
  try {
    await checkDevPort(url);
  } catch (error) {
    const reason = error.code === "EADDRINUSE"
      ? "포트가 이미 사용 중입니다. 실행 중인 개발 서버를 먼저 종료하세요."
      : `포트를 열 수 없습니다 (${error.code}).`;
    console.error(`[dev] ${url.host}: ${reason}`);
    process.exitCode = 1;
  }
}
