// The tiny fake server: it replays one recorded exchange file from exchanges/ and
// notes every way the library's requests differ from the recorded ones.
import { isDeepStrictEqual } from "node:util";
import { createServer } from "node:http";
import { readdir, readFile } from "node:fs/promises";

const EXCHANGES = new URL("../../exchanges/", import.meta.url);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CHUNK_PAUSE_MS = 5;

export async function loadExchanges() {
  const names = (await readdir(EXCHANGES)).filter((name) => name.endsWith(".json")).sort();
  return Promise.all(
    names.map(async (name) => ({ name, ...JSON.parse(await readFile(new URL(name, EXCHANGES), "utf8")) })),
  );
}

export async function replay(recording, { key }) {
  const problems = [];
  let next = 0;
  let base = "";
  const fill = (value) => value.replaceAll("{base}", base).replaceAll("{key}", key);

  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const sent = Buffer.concat(chunks).toString("utf8");
    const step = recording.exchanges[next++];
    if (!step) {
      problems.push(`unexpected ${req.method} ${req.url}`);
      res.writeHead(500).end();
      return;
    }
    const { request, response } = step;
    if (req.method !== request.method || req.url !== request.path) {
      problems.push(`#${next}: expected ${request.method} ${request.path}, got ${req.method} ${req.url}`);
    }
    for (const [name, value] of Object.entries(request.headers ?? {})) {
      const got = req.headers[name.toLowerCase()];
      const ok = value === "{uuid}" ? UUID.test(got ?? "") : got === fill(value);
      if (!ok) problems.push(`#${next}: header ${name} is ${JSON.stringify(got)}`);
    }
    if (request.body !== undefined && !isDeepStrictEqual(parseOrText(sent), request.body)) {
      problems.push(`#${next}: body is ${sent}`);
    }

    const headers = { "Content-Type": "application/json" };
    for (const [name, value] of Object.entries(response.headers ?? {})) headers[name] = fill(value);
    res.writeHead(response.status, headers);
    res.flushHeaders();
    for (const chunk of response.chunks ?? []) {
      await pause();
      res.write(chunk);
    }
    if (response.cut) {
      await pause();
      res.socket.destroy();
    } else {
      res.end(JSON.stringify(response.body));
    }
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${server.address().port}`;
  return {
    base,
    problems,
    remaining: () => recording.exchanges.length - next,
    close: () => {
      server.closeAllConnections();
      return new Promise((resolve) => server.close(resolve));
    },
  };
}

function parseOrText(text) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function pause() {
  return new Promise((resolve) => setTimeout(resolve, CHUNK_PAUSE_MS));
}
