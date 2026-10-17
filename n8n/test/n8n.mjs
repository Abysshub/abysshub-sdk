// A stand-in for what n8n hands a node: its parameters, its credential, and the HTTP
// helpers, which behave as n8n's do. `httpRequest` answers `{ body, headers, statusCode }`
// with `returnFullResponse`, parses JSON with `json`, gives a Buffer with `encoding:
// "arraybuffer"`, and throws when the connection drops or is cut. The authenticated helper
// applies the credential's `authenticate` headers, as n8n does for a generic credential.
import { createRequire } from "node:module";
import { basename } from "node:path";

const require = createRequire(import.meta.url);
export const { Abyss } = require("../dist/nodes/Abyss/Abyss.node.js");
export const { AbyssApi } = require("../dist/credentials/AbyssApi.credentials.js");

const credentialType = new AbyssApi();

/** A credential expression such as `=Bearer {{$credentials.apiKey}}`, filled in. */
export function resolve(expression, credentials) {
  if (typeof expression !== "string" || !expression.startsWith("=")) return expression;
  return expression.slice(1).replace(/\{\{\s*\$credentials\.(\w+)\s*\}\}/g, (_, name) => String(credentials[name]));
}

export async function httpRequest(options) {
  const url = options.baseURL ? `${options.baseURL.replace(/\/+$/, "")}${options.url}` : options.url;
  const headers = { ...options.headers };
  let body;
  if (options.body !== undefined) {
    body = JSON.stringify(options.body);
    headers["Content-Type"] ??= "application/json";
  }
  const response = await fetch(url, { method: options.method ?? "GET", headers, body, signal: options.abortSignal });
  const bytes = Buffer.from(await response.arrayBuffer());
  let data = options.encoding === "arraybuffer" ? bytes : bytes.toString("utf8");
  if (options.json && typeof data === "string" && data.trim() !== "") {
    try {
      data = JSON.parse(data);
    } catch {}
  }
  if (!options.ignoreHttpStatusErrors && response.status >= 400) {
    throw Object.assign(new Error(`Request failed with status code ${response.status}`), { httpCode: String(response.status) });
  }
  if (!options.returnFullResponse) return data;
  return { body: data, headers: Object.fromEntries(response.headers), statusCode: response.status, statusMessage: response.statusText };
}

/** The headers the credential's `authenticate` adds to a request. */
export function authenticated(options, credentials) {
  const added = Object.fromEntries(
    Object.entries(credentialType.authenticate.properties.headers).map(([name, value]) => [name, resolve(value, credentials)]),
  );
  return { ...options, headers: { ...options.headers, ...added } };
}

/** The node's declared defaults. */
const DEFAULTS = Object.fromEntries(new Abyss().description.properties.map(({ name, default: value }) => [name, value]));

/**
 * Runs the node once over `items`, as n8n would, and answers its output items.
 * `parameters` is the node's parameters, or a function answering an item's, as
 * expressions resolve per item.
 */
export function execute({ parameters, credentials, items = [{ json: {} }], continueOnFail = false }) {
  const valuesFor = (itemIndex) => ({ ...DEFAULTS, ...(typeof parameters === "function" ? parameters(items[itemIndex]) : parameters) });
  const node = { id: "abyss", name: "Abyss", type: "n8n-nodes-abysshub.abyss", typeVersion: 1, position: [0, 0], parameters: {} };
  const context = {
    getInputData: () => items,
    getNode: () => node,
    getNodeParameter: (name, itemIndex, fallback) => {
      const values = valuesFor(itemIndex);
      if (name in values) return values[name];
      if (fallback === undefined) throw new Error(`no parameter ${name}`);
      return fallback;
    },
    getCredentials: async (name) => {
      if (name !== credentialType.name) throw new Error(`no credential ${name}`);
      return credentials;
    },
    getExecutionCancelSignal: () => undefined,
    continueOnFail: () => continueOnFail,
    helpers: {
      httpRequest,
      async httpRequestWithAuthentication(name, options) {
        if (name !== credentialType.name) throw new Error(`no credential ${name}`);
        return httpRequest(authenticated(options, credentials));
      },
      async prepareBinaryData(buffer, filePath, mimeType) {
        return { data: buffer.toString("base64"), mimeType, fileName: basename(filePath), fileSize: String(buffer.length) };
      },
    },
  };
  return new Abyss().execute.call(context).then(([output]) => output);
}
