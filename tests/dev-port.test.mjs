import assert from "node:assert/strict";
import { createServer } from "node:net";
import { once } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { checkDevPort } from "../scripts/check-dev-port.mjs";

test("port guard preserves an existing server and releases a successful probe", async (t) => {
  const server = createServer();
  t.after(() => server.listening && server.close());
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const url = new URL(`http://127.0.0.1:${server.address().port}`);
  await assert.rejects(checkDevPort(url), { code: "EADDRINUSE" });
  assert.equal(server.listening, true);
  await new Promise((resolve) => server.close(resolve));
  await checkDevPort(url);
  server.listen(Number(url.port), url.hostname);
  await once(server, "listening");
  assert.equal(server.listening, true);
});

test("the development server serves the app and transforms Vue with a cold cache", { timeout: 15_000 }, async () => {
  const { createServer: createViteServer } = await import("vite");
  const cacheDir = await mkdtemp(join(tmpdir(), "ai-asset-hub-vite-"));
  const server = await createViteServer({ cacheDir, server: { port: 0 } });
  try {
    await server.listen();
    const { port } = server.httpServer.address();
    for (const [path, marker] of [
      ["/", /id="app"/],
      ["/src/main.ts", /createApp/],
      ["/src/views/LibraryView.vue", /library-workspace/],
    ]) {
      const response = await fetch(`http://127.0.0.1:${port}${path}`, { signal: AbortSignal.timeout(5_000) });
      assert.equal(response.status, 200, path);
      assert.match(await response.text(), marker, path);
    }
  } finally {
    await server.close();
    await rm(cacheDir, { recursive: true, force: true });
  }
});
