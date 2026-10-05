# Recorded exchanges

Each file is one call through a library and the HTTP exchanges it makes, in order. Both libraries replay every file through a tiny fake server and must reach the same `outcome`. The JS tests also validate every recorded body against `contract/openapi.json`.

- **`call`:** what the caller does: `abyss.run(call.widget, call.input)`, with `call.options` (`max_price`, `idempotency_key`) in each language's own spelling.
  - **`files`:** the caller's files, by name, with their text content. The test writes them to a folder first.
  - **File values in `input`:** `{"$file": name}` is `file(path)` for that file. `{"$bytes": name}` is its content in memory, given with its name: a `File` in JS. A list may mix them with plain strings.
  - **`save`:** after the run, the caller calls `run.save(<folder>/<save>)`.
- **`exchanges[]`:** the requests the library must send, each with the response the fake server replays.
  - **`request`:** `method`, `path` (with its query), `headers` the library must send, and the JSON `body` it must send, if any. A storage upload has `form` instead: each form field's text, and `file`, the file's content, which must come last.
  - **`response`:** `status` and `headers`, sent at once. Then each of `chunks` (the spaces a hold sends), then `body` as JSON, or `text` as it is. With `"cut": true` there is no `body`: the connection is cut after the chunks. With `"drop": true` there is nothing at all: the connection is cut before any headers.
  - **`"storage": true`:** the request goes to storage (S3), not to `/v1`: an upload form, or an output file's download. It must not carry the API key, and the contract does not apply to it.
  - **`"parallel": true`:** consecutive exchanges marked so may arrive in any order. Each request is matched to the one it fits.
- **`outcome`:** either `run`, fields the returned run must have, or `error`, the fields the raised `AbyssError` must carry. Its `run` is the fields of the run it carries, or `null` for none. With `call.save`, `saved` is every file `run.save()` must write, by its path under the folder, with its content; `run.save()` answers those paths in this order.

Placeholders, filled in by the fake server in headers and bodies: `{base}` is its address, and `{key}` is the API key the test gives the client. `{uuid}` matches any UUID, and the same one each time it appears in a recording: a call presses with one `Idempotency-Key`, retries included.
