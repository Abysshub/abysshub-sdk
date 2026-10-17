import { randomUUID } from 'crypto';
import type {
	IBinaryKeyData,
	IDataObject,
	IExecuteFunctions,
	IHttpRequestMethods,
	IN8nHttpFullResponse,
	JsonObject,
} from 'n8n-workflow';
import { NodeApiError, NodeOperationError, sleepWithAbort } from 'n8n-workflow';

/** One file a run wrote, as `/v1` answers it. */
export interface RunFile extends IDataObject {
	path: string;
	size: number;
	content_type: string;
	url: string;
}

/** A run, as `/v1` answers it. */
export interface Run extends IDataObject {
	id: string;
	status: 'queued' | 'running' | 'succeeded' | 'failed';
	output_files: RunFile[];
	files: 'ready' | 'asleep' | 'waking';
	error: { code: string; message: string } | null;
}

export interface PressOptions {
	wait: boolean;
	maxPrice?: number;
	idempotencyKey?: string;
}

interface Answer {
	status: number;
	headers: IDataObject;
	body: unknown;
}

const DEFAULT_URL = 'https://api.abysshub.com';

/** A press and a read are sent again at most this many times. */
const MAX_RETRIES = 2;

/** The pause between two re-attaches that both ended without the run's ending. */
const REATTACH_PAUSE_MS = 1_000;

/** The first pause before a retry after a drop or a 5xx; it doubles with each retry. */
const RETRY_PAUSE_MS = 500;

/** The longest pause between two tries, which only re-attaching, with no limit, reaches. */
const RETRY_PAUSE_CEILING_MS = 10_000;

/**
 * Presses a Widget. With `wait`, the press holds until the run ends; a `202` or a `200`
 * still `running` is followed by `GET /v1/runs/{id}?wait=true`, read again with no limit
 * until the run ends, and a failed run raises. Without `wait`, it answers the queued run.
 */
export async function runWidget(
	ctx: IExecuteFunctions,
	itemIndex: number,
	widget: string,
	input: IDataObject,
	options: PressOptions,
): Promise<Run> {
	const base = await baseUrl(ctx);
	const body: IDataObject = { input };
	if (options.maxPrice !== undefined) body.max_price = options.maxPrice;
	if (!options.wait) body.wait = false;
	// One Idempotency-Key for every try: a press sent again after a drop or a cut hold
	// answers the same run, and holds again.
	const headers = { 'Idempotency-Key': options.idempotencyKey ?? randomUUID() };
	const url = `${base}/v1/widgets/${encodeURIComponent(widget)}/runs`;
	let answer = await send(ctx, itemIndex, 'POST', url, MAX_RETRIES, body, headers);
	let run = expectRun(ctx, itemIndex, answer);
	if (!options.wait) return run;

	const waitUrl = `${base}/v1/runs/${encodeURIComponent(run.id)}?wait=true`;
	for (let reattach = 0; !hasEnded(run); reattach++) {
		if (reattach > 0) await sleepWithAbort(REATTACH_PAUSE_MS, ctx.getExecutionCancelSignal());
		answer = await send(ctx, itemIndex, 'GET', waitUrl, Infinity);
		run = expectRun(ctx, itemIndex, answer);
	}
	if (run.status === 'failed') {
		throw new NodeOperationError(ctx.getNode(), run.error?.message ?? 'The run failed.', {
			description: describe(run.error?.code ?? 'platform_fault', run.id, answer.headers['request-id']),
			itemIndex,
		});
	}
	return run;
}

/** Reads a run as it is now, with `GET /v1/runs/{id}`. */
export async function getRun(ctx: IExecuteFunctions, itemIndex: number, id: string): Promise<Run> {
	const url = `${await baseUrl(ctx)}/v1/runs/${encodeURIComponent(id)}`;
	return expectRun(ctx, itemIndex, await send(ctx, itemIndex, 'GET', url, MAX_RETRIES));
}

/**
 * Downloads every output file of the run as binary data, `file_0`, `file_1`, … in the
 * order of `output_files`. An expired URL is refreshed once by reading the run again.
 */
export async function downloadOutputFiles(ctx: IExecuteFunctions, itemIndex: number, run: Run): Promise<IBinaryKeyData> {
	if (run.files === 'asleep' || run.files === 'waking') {
		const message =
			run.files === 'asleep'
				? `The files of run ${run.id} are asleep. Wake the run with POST /v1/runs/${run.id}/wake: they are back within 12 hours.`
				: `The files of run ${run.id} are waking: they are back within 12 hours.`;
		throw new NodeOperationError(ctx.getNode(), message, { description: `files_${run.files}`, itemIndex });
	}
	const binary: IBinaryKeyData = {};
	let files = run.output_files;
	let refreshed = false;
	for (let index = 0; index < files.length; index++) {
		let file = files[index] as RunFile;
		let answer = await download(ctx, file.url);
		if (answer.statusCode === 403 && !refreshed) {
			refreshed = true;
			files = (await getRun(ctx, itemIndex, run.id)).output_files;
			file = files.find(({ path }) => path === file.path) ?? file;
			answer = await download(ctx, file.url);
		}
		if (answer.statusCode !== 200) {
			throw new NodeOperationError(ctx.getNode(), `Could not download ${file.path}: storage answered ${answer.statusCode}.`, {
				itemIndex,
			});
		}
		binary[`file_${index}`] = await ctx.helpers.prepareBinaryData(
			Buffer.from(answer.body as Buffer),
			file.path,
			file.content_type,
		);
	}
	return binary;
}

async function baseUrl(ctx: IExecuteFunctions): Promise<string> {
	const credentials = await ctx.getCredentials('abyssApi');
	const url = typeof credentials.url === 'string' && credentials.url.trim() !== '' ? credentials.url.trim() : DEFAULT_URL;
	return url.replace(/\/+$/, '');
}

/** An output file's signed URL is storage's, not `/v1`'s: it is read without the API key. */
function download(ctx: IExecuteFunctions, url: string): Promise<IN8nHttpFullResponse> {
	return ctx.helpers.httpRequest({
		method: 'GET',
		url,
		encoding: 'arraybuffer',
		returnFullResponse: true,
		ignoreHttpStatusErrors: true,
		abortSignal: ctx.getExecutionCancelSignal(),
	}) as Promise<IN8nHttpFullResponse>;
}

/**
 * Sends one request to `/v1`. A drop or a cut, a `429`, a `409` and a `5xx` are sent
 * again, at most `retries` times; every other refusal raises at once with the API's message.
 */
async function send(
	ctx: IExecuteFunctions,
	itemIndex: number,
	method: IHttpRequestMethods,
	url: string,
	retries: number,
	body?: IDataObject,
	headers?: IDataObject,
): Promise<Answer> {
	const signal = ctx.getExecutionCancelSignal();
	for (let attempt = 0; ; attempt++) {
		let response: IN8nHttpFullResponse;
		try {
			response = (await ctx.helpers.httpRequestWithAuthentication.call(ctx, 'abyssApi', {
				method,
				url,
				headers: { Accept: 'application/json', ...headers },
				...(body === undefined ? {} : { body }),
				json: true,
				returnFullResponse: true,
				ignoreHttpStatusErrors: true,
				abortSignal: signal,
			})) as IN8nHttpFullResponse;
		} catch (error) {
			if (signal?.aborted || attempt >= retries) {
				throw new NodeApiError(ctx.getNode(), error as JsonObject, {
					message: 'The connection to the Abyss API dropped before it answered.',
					itemIndex,
				});
			}
			await sleepWithAbort(backoff(attempt), signal);
			continue;
		}
		const answer: Answer = { status: response.statusCode, headers: response.headers, body: parse(response.body) };
		if (answer.status < 400) return answer;
		const pause = retryPause(answer, attempt);
		if (pause === null || attempt >= retries) throw refusal(ctx, itemIndex, answer);
		await sleepWithAbort(pause, signal);
	}
}

/** How long to wait before sending a refused request again, or null when it is not retried. */
function retryPause(answer: Answer, attempt: number): number | null {
	if (answer.status === 429 || answer.status === 409) {
		const seconds = Number(answer.headers['retry-after'] ?? Number.NaN);
		return Number.isFinite(seconds) && seconds >= 0 ? seconds * 1_000 : backoff(attempt);
	}
	return answer.status >= 500 ? backoff(attempt) : null;
}

function backoff(attempt: number): number {
	return Math.min(RETRY_PAUSE_MS * 2 ** attempt, RETRY_PAUSE_CEILING_MS);
}

/** A refusal as an n8n error carrying the API's message, its code and its request id. */
function refusal(ctx: IExecuteFunctions, itemIndex: number, answer: Answer): NodeApiError {
	const body = isObject(answer.body) ? answer.body : {};
	const error = isObject(body.error) ? body.error : {};
	const requestId = typeof body.request_id === 'string' ? body.request_id : answer.headers['request-id'];
	const description = describe(error.code, undefined, requestId);
	return new NodeApiError(ctx.getNode(), body as JsonObject, {
		message: typeof error.message === 'string' ? error.message : `The Abyss API answered ${answer.status}.`,
		...(description === '' ? {} : { description }),
		httpCode: String(answer.status),
		itemIndex,
	});
}

/** An error's description, such as `invalid_input · request req_…`, from the parts it has. */
function describe(code: unknown, runId: string | undefined, requestId: unknown): string {
	const parts = [code, runId && `run ${runId}`, requestId && `request ${String(requestId)}`];
	return parts.filter((part) => typeof part === 'string' && part !== '').join(' · ');
}

function expectRun(ctx: IExecuteFunctions, itemIndex: number, answer: Answer): Run {
	const { body } = answer;
	if (isObject(body) && typeof body.id === 'string' && typeof body.status === 'string' && Array.isArray(body.output_files)) {
		return body as Run;
	}
	throw new NodeOperationError(ctx.getNode(), 'The Abyss API answered without a run.', { itemIndex });
}

function hasEnded(run: Run): boolean {
	return run.status === 'succeeded' || run.status === 'failed';
}

/** A held answer starts with spaces; JSON allows them, but a body left as text is parsed here. */
function parse(body: unknown): unknown {
	if (typeof body !== 'string') return body;
	try {
		return JSON.parse(body);
	} catch {
		return body;
	}
}

function isObject(value: unknown): value is IDataObject {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}
