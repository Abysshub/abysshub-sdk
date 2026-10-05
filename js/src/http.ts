export interface Limits {
  /** How long to wait for the status and headers. */
  connectMs: number;
  /** How long the body may stay silent before it counts as a cut. */
  silenceMs: number;
}

export const LIMITS: Limits = { connectMs: 10_000, silenceMs: 30_000 };

export interface Answer {
  status: number;
  headers: Headers;
  /** The whole body, or null when the connection was cut or went silent after the headers. */
  text: string | null;
}

/**
 * Sends one request and reads its whole body. A failure before the headers rejects;
 * a cut after them answers `text: null`, so the caller can re-attach. `init.signal`
 * stops the request at any point, and then it always rejects.
 */
export async function request(url: string, init: RequestInit, limits: Limits = LIMITS): Promise<Answer> {
  const stop = init.signal;
  stop?.throwIfAborted();
  const controller = new AbortController();
  const abort = () => controller.abort();
  stop?.addEventListener("abort", abort, { once: true });
  const connect = setTimeout(abort, limits.connectMs);
  try {
    let response: Response;
    try {
      response = await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(connect);
    }
    const text = await readBody(response, controller, limits.silenceMs);
    stop?.throwIfAborted();
    return { status: response.status, headers: response.headers, text };
  } finally {
    stop?.removeEventListener("abort", abort);
  }
}

async function readBody(response: Response, controller: AbortController, silenceMs: number): Promise<string | null> {
  if (!response.body) return "";
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let silence: ReturnType<typeof setTimeout> | undefined;
  const listen = () => {
    clearTimeout(silence);
    silence = setTimeout(() => controller.abort(), silenceMs);
  };
  try {
    listen();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return text + decoder.decode();
      listen();
      text += decoder.decode(value, { stream: true });
    }
  } catch {
    return null;
  } finally {
    clearTimeout(silence);
  }
}
