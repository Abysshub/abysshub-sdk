# Recorded exchanges

Each file is one call through a library and the HTTP exchanges it makes, in order. Both libraries replay every file through a tiny fake server and must reach the same `outcome`. The JS tests also validate every recorded body against `contract/openapi.json`.

- **`call`:** what the caller does: `abyss.run(call.widget, call.input)`, with `call.options` (`max_price`, `idempotency_key`) in each language's own spelling.
- **`exchanges[]`:** the requests the library must send, each with the response the fake server replays.
  - **`request`:** `method`, `path` (with its query), `headers` the library must send, and the JSON `body` it must send, if any.
  - **`response`:** `status` and `headers`, sent at once. Then each of `chunks` (the spaces a hold sends), then `body` as JSON. With `"cut": true` there is no `body`: the connection is cut after the chunks.
- **`outcome`:** either `run`, fields the returned run must have, or `error`, the fields the raised `AbyssError` must carry. Its `run` is the fields of the run it carries, or `null` for none.

Placeholders, filled in by the fake server: `{base}` is its address, `{key}` is the API key the test gives the client, and `{uuid}` matches any UUID.
