// Every recorded request and response body, and every recorded header, is held to
// contract/openapi.json, so the exchanges both libraries replay are ones /v1 can send.
// Storage exchanges (S3 uploads and downloads) are not /v1's, and a drop sends nothing.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { fillEvery, loadExchanges } from "./fake-server.js";

const contract = JSON.parse(await readFile(new URL("../../contract/openapi.json", import.meta.url), "utf8"));
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema(contract, "openapi.json");

const BASE = contract.servers[0].url;
const UUID = "5f0c3b9e-1d7a-4c2e-9a61-0b8f2d4e7c13";
const fill = (value) => value.replaceAll("{base}", BASE).replaceAll("{key}", "abyss_sk_x").replaceAll("{uuid}", UUID);

function resolve(node) {
  while (node?.$ref) node = node.$ref.slice(2).split("/").reduce((at, key) => at[key], contract);
  return node;
}

function validator(pointer, what) {
  const validate = ajv.getSchema(`openapi.json#${pointer}`);
  return (value) => assert.ok(validate(value), `${what}: ${ajv.errorsText(validate.errors)}`);
}

// Query and header values arrive as text; a boolean or integer schema needs the typed value.
function coerce(schema, text) {
  if (schema.type === "boolean") return text === "true" ? true : text === "false" ? false : text;
  if (schema.type === "integer") return Number(text);
  return text;
}

function operation(method, path) {
  for (const [template, item] of Object.entries(contract.paths)) {
    const pattern = new RegExp(`^${template.replace(/\{[^}]+\}/g, "[^/]+")}$`);
    if (pattern.test(path) && item[method.toLowerCase()]) return { template, op: item[method.toLowerCase()] };
  }
  assert.fail(`${method} ${path} is not in the contract`);
}

for (const recording of await loadExchanges()) {
  test(`contract: ${recording.name}`, () => {
    recording.exchanges.forEach(({ storage, request, response }, index) => {
      const at = `exchange #${index + 1}`;
      if (storage) return;
      const url = new URL(request.path, BASE);
      const { template, op } = operation(request.method, url.pathname);
      const params = (op.parameters ?? []).map(resolve);

      for (const [name, value] of url.searchParams) {
        const param = params.find((p) => p.in === "query" && p.name === name);
        assert.ok(param, `${at}: ${template} takes no query ${name}`);
        assert.ok(ajv.validate(param.schema, coerce(param.schema, value)), `${at}: query ${name}: ${ajv.errorsText()}`);
      }
      for (const [name, value] of Object.entries(request.headers ?? {})) {
        const param = params.find((p) => p.in === "header" && p.name.toLowerCase() === name.toLowerCase());
        if (!param) continue;
        assert.ok(ajv.validate(param.schema, fill(value)), `${at}: header ${name}: ${ajv.errorsText()}`);
      }
      if (request.body !== undefined) {
        const pointer = `/paths/${template.replaceAll("/", "~1")}/${request.method.toLowerCase()}/requestBody/content/application~1json/schema`;
        assert.ok(op.requestBody?.content?.["application/json"], `${at}: ${template} takes no JSON body`);
        validator(pointer, `${at}: request body`)(request.body);
      }

      if (response.drop) return;
      const answer = op.responses[String(response.status)];
      assert.ok(answer, `${at}: ${template} does not answer ${response.status}`);
      const declared = resolve(answer);
      for (const [name, header] of Object.entries(declared.headers ?? {})) {
        const schema = resolve(header);
        const sent = Object.entries(response.headers ?? {}).find(([key]) => key.toLowerCase() === name.toLowerCase());
        if (!sent) {
          assert.ok(!schema.required, `${at}: the ${response.status} must send ${name}`);
          continue;
        }
        assert.ok(ajv.validate(schema.schema, coerce(schema.schema, fill(sent[1]))), `${at}: header ${name}: ${ajv.errorsText()}`);
      }
      if (response.cut || response.hold) {
        assert.equal(response.body, undefined, `${at}: a cut or a hold has no body`);
      } else {
        const ref = declared.content?.["application/json"]?.schema?.$ref;
        assert.ok(ref, `${at}: the ${response.status} has no JSON body in the contract`);
        validator(ref.slice(1), `${at}: response body`)(fillEvery(response.body, fill));
      }
      for (const chunk of response.chunks ?? []) assert.match(chunk, /^ +$/, `${at}: a hold's chunks are spaces`);
    });
  });
}
