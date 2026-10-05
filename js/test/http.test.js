import assert from "node:assert/strict";
import { createServer } from "node:http";
import { test } from "node:test";
import { request } from "../dist/http.js";

async function serve(handler) {
  const server = createServer(handler);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return {
    url: `http://127.0.0.1:${server.address().port}/`,
    close: () => {
      server.closeAllConnections();
      return new Promise((resolve) => server.close(resolve));
    },
  };
}

test("silence after the headers counts as a cut", async () => {
  const server = await serve((req, res) => {
    res.writeHead(200);
    res.write(" ");
  });
  try {
    const answer = await request(server.url, {}, { connectMs: 1_000, silenceMs: 100 });
    assert.equal(answer.status, 200);
    assert.equal(answer.text, null);
  } finally {
    await server.close();
  }
});

test("no headers within the connect limit rejects", async () => {
  const server = await serve(() => {});
  try {
    await assert.rejects(request(server.url, {}, { connectMs: 100, silenceMs: 1_000 }));
  } finally {
    await server.close();
  }
});

test("a whole body keeps its leading spaces for the caller to skip", async () => {
  const server = await serve((req, res) => {
    res.writeHead(200);
    res.write("  ");
    res.end('{"ok":true}');
  });
  try {
    const answer = await request(server.url, {}, { connectMs: 1_000, silenceMs: 1_000 });
    assert.deepEqual(JSON.parse(answer.text), { ok: true });
  } finally {
    await server.close();
  }
});
