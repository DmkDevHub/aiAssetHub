import assert from "node:assert/strict";
import { createServer } from "node:net";
import { once } from "node:events";
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
