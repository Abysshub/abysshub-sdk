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
  const served = new Set();
  let uuid = null;
  let base = "";
  const fill = (value) => value.replaceAll("{base}", base).replaceAll("{key}", key);
  const fillAll = (value) =>
    typeof value === "string"
      ? fill(value)
      : Array.isArray(value)
        ? value.map(fillAll)
        : value && typeof value === "object"
          ? Object.fromEntries(Object.entries(value).map(([name, item]) => [name, fillAll(item)]))
          : value;

  // The exchanges the next request may answer: the first one not yet served, or every
  // unserved one in its block when it is marked `parallel`.
  const candidates = () => {
    const first = recording.exchanges.findIndex((_, index) => !served.has(index));
    if (first < 0 || !recording.exchanges[first].parallel) return first < 0 ? [] : [first];
    const block = [];
    for (let index = first; recording.exchanges[index]?.parallel; index++) if (!served.has(index)) block.push(index);
    return block;
  };

  const differences = async (index, req, sent) => {
    const { storage, request } = recording.exchanges[index];
    const found = [];
    if (req.method !== request.method || req.url !== request.path) {
      found.push(`expected ${request.method} ${request.path}, got ${req.method} ${req.url}`);
    }
    for (const [name, value] of Object.entries(request.headers ?? {})) {
      const got = req.headers[name.toLowerCase()];
      const ok = value === "{uuid}" ? UUID.test(got ?? "") && (uuid === null || got === uuid) : got === fill(value);
      if (!ok) found.push(`header ${name} is ${JSON.stringify(got)}`);
    }
    if (storage && req.headers.authorization !== undefined) found.push("storage was sent the API key");
    if (request.body !== undefined && !isDeepStrictEqual(parseOrText(sent.toString("utf8")), request.body)) {
      found.push(`body is ${sent.toString("utf8")}`);
    }
    if (request.form !== undefined) {
      const form = await readForm(req, sent);
      if (!isDeepStrictEqual(form, request.form)) found.push(`form is ${JSON.stringify(form)}`);
    }
    return found;
  };

  // Serves the request with the candidate it matches, else the first one, noting why.
  // Requests are matched one at a time, since parallel ones may arrive together.
  let choosing = Promise.resolve(null);
  const choose = async (req, sent) => {
    const open = candidates();
    if (open.length === 0) return null;
    let index = open[0];
    let found = await differences(index, req, sent);
    for (const other of open.slice(1)) {
      if (found.length === 0) break;
      if ((await differences(other, req, sent)).length === 0) {
        index = other;
        found = [];
      }
    }
    served.add(index);
    for (const problem of found) problems.push(`#${index + 1}: ${problem}`);
    for (const [name, value] of Object.entries(recording.exchanges[index].request.headers ?? {})) {
      if (value === "{uuid}") uuid ??= req.headers[name.toLowerCase()];
    }
    return index;
  };

  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const sent = Buffer.concat(chunks);
    const index = await (choosing = choosing.then(() => choose(req, sent)));
    if (index === null) {
      problems.push(`unexpected ${req.method} ${req.url}`);
      res.writeHead(500).end();
      return;
    }
    const { response } = recording.exchanges[index];

    if (response.drop) {
      res.socket.destroy();
      return;
    }
    const headers = response.body === undefined ? {} : { "Content-Type": "application/json" };
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
    } else if (response.body !== undefined) {
      res.end(JSON.stringify(fillAll(response.body)));
    } else {
      res.end(response.text ?? "");
    }
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${server.address().port}`;
  return {
    base,
    problems,
    remaining: () => recording.exchanges.length - served.size,
    close: () => {
      server.closeAllConnections();
      return new Promise((resolve) => server.close(resolve));
    },
  };
}

// A storage upload form, as the recordings write it: each field's text, with the file
// (which must come last) as its content.
async function readForm(req, sent) {
  try {
    const entries = [...(await new Response(sent, { headers: { "Content-Type": req.headers["content-type"] } }).formData())];
    const form = {};
    for (const [name, value] of entries) form[name] = typeof value === "string" ? value : await value.text();
    if (entries.at(-1)?.[0] !== "file") form["(the file is not last)"] = true;
    return form;
  } catch (error) {
    return { "(not a form)": String(error) };
  }
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
