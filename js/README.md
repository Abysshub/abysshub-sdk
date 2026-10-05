# abysshub

The official JavaScript library for the [Abyss](https://abysshub.com) API.

Pre-release: the Abyss API opens soon.

```js
import { Abyss, AbyssError } from "abysshub";

const abyss = new Abyss(); // reads ABYSS_API_KEY

try {
  const run = await abyss.run("widget_131", { amount: 250000 });
  console.log(run.result);
} catch (error) {
  if (error instanceof AbyssError) console.error(error.code, error.param, error.request_id, error.run);
  else throw error;
}
```

`run()` presses the Widget and waits for the run to end, however long it takes, then returns the succeeded run. A refusal or a failed run raises `AbyssError`.

- **`new Abyss({ apiKey?, baseURL?, maxRetries? })`:** the key defaults to `ABYSS_API_KEY`. A key starting `abyss_sk_dev_` goes to `https://api.dev.abysshub.com`. `ABYSS_BASE_URL` or `baseURL` overrides the address.
- **`abyss.run(widget, input, { maxPrice?, idempotencyKey? })`:** each call presses with a fresh UUID `Idempotency-Key` unless you give one.
- **Names:** returned data keeps the API's names (`output_files`, `request_id`). Options are camelCase. Field names are never converted.
