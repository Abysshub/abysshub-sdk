# n8n-nodes-abysshub

Pre-release: the Abyss API opens soon, and this package is not published yet.

An [n8n](https://n8n.io) community node that runs an [Abyss](https://abysshub.com) Widget as a step in a workflow. It gives n8n one node, **Abyss**, with one credential.

## Credentials

**Abyss API** takes:

- **API Key:** an API key from your Cave, starting `abyss_sk_`.
- **API URL:** `https://api.abysshub.com` by default. A key starting `abyss_sk_dev_` needs `https://api.dev.abysshub.com`.

Saving the credential tests it with `GET /v1/key`.

## Operations

- **Run a Widget** takes a **Widget ID** (`widget_<id>`, or an unlisted Widget's private token) and its **Input** as a JSON object of its fields by name, and returns the run object.
  - **Wait for Result**, on by default, ends the step when the run ends. A failed run fails the step with the run's error message. Off, the step returns the queued run at once: read it later with **Get a Run**.
  - **Options:** **Max Price**, the most you will pay for the run, and **Idempotency Key**: a press repeated with the same key and input within 24 hours returns the same run.
- **Get a Run** takes a **Run ID** and returns the run object as it is now.

## Files

- **Input files:** give a file field an `https` link to the file, as a string in the input.
- **Output files:** the run object lists them in `output_files`, each with a signed `url` that expires. **Download Output Files** also attaches every one to the item as binary data, `file_0`, `file_1` and so on in that order, so the next node can mail or store them. A run whose files are asleep fails the download: wake it with `POST /v1/runs/{id}/wake` first.

## Errors

An error from the API fails the step with the API's message. Its description gives the error's `code` and the `request_id` to quote to support. With **Continue On Fail**, the item carries `{ "error": message }` instead.

## Development

`npm test` builds the package, replays the recorded exchanges in [`exchanges/`](../exchanges) through the node, and runs `npm run scan`. The scan applies the rules of `npx @n8n/scan-community-package`, which only scans a published package, to the sources and to the built package. Installing the dev tools runs no install scripts (`.npmrc`), since one of the scanner's dependencies builds only on Node 22.
