import type {
	IDataObject,
	IExecuteFunctions,
	INodeExecutionData,
	INodeType,
	INodeTypeDescription,
} from 'n8n-workflow';
import { NodeApiError, NodeConnectionTypes, NodeOperationError, jsonParse } from 'n8n-workflow';
import { downloadOutputFiles, getRun, runWidget } from './api';
import type { PressOptions, Run } from './api';

export class Abyss implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'Abyss',
		name: 'abyss',
		icon: 'file:abyss.svg',
		group: ['transform'],
		version: 1,
		subtitle: '={{$parameter["operation"] === "get" ? "Get a run" : "Run a Widget"}}',
		description: 'Run an Abyss Widget and read its runs',
		defaults: {
			name: 'Abyss',
		},
		usableAsTool: true,
		inputs: [NodeConnectionTypes.Main],
		outputs: [NodeConnectionTypes.Main],
		credentials: [
			{
				name: 'abyssApi',
				required: true,
			},
		],
		properties: [
			{
				displayName: 'Operation',
				name: 'operation',
				type: 'options',
				noDataExpression: true,
				options: [
					{
						name: 'Run a Widget',
						value: 'run',
						description: 'Start a run of a Widget and return the run',
						action: 'Run a widget',
					},
					{
						name: 'Get a Run',
						value: 'get',
						description: 'Return a run as it is now',
						action: 'Get a run',
					},
				],
				default: 'run',
			},
			{
				displayName: 'Widget ID',
				name: 'widgetId',
				type: 'string',
				required: true,
				default: '',
				placeholder: 'widget_131',
				description: 'The Widget to run: its ID, or the private token of an unlisted Widget',
				displayOptions: { show: { operation: ['run'] } },
			},
			{
				displayName: 'Input',
				name: 'input',
				type: 'json',
				default: '{}',
				description:
					"The Widget's input as a JSON object of its fields by name. A file field takes an https link to the file.",
				displayOptions: { show: { operation: ['run'] } },
			},
			{
				displayName: 'Wait for Result',
				name: 'waitForResult',
				type: 'boolean',
				default: true,
				description:
					'Whether to end the step when the run ends, returning the ended run. Off, the step returns the queued run at once.',
				displayOptions: { show: { operation: ['run'] } },
			},
			{
				displayName: 'Run ID',
				name: 'runId',
				type: 'string',
				required: true,
				default: '',
				placeholder: 'run_8fK2mQx7Lp3Rz9Tb4Wc6Yd1N',
				description: 'The ID of the run to return',
				displayOptions: { show: { operation: ['get'] } },
			},
			{
				displayName: 'Download Output Files',
				name: 'downloadOutputFiles',
				type: 'boolean',
				default: false,
				description:
					'Whether to attach every output file of the run to the item as binary data, as file_0, file_1 and so on',
			},
			{
				displayName: 'Options',
				name: 'options',
				type: 'collection',
				placeholder: 'Add Option',
				default: {},
				displayOptions: { show: { operation: ['run'] } },
				options: [
					{
						displayName: 'Idempotency Key',
						name: 'idempotencyKey',
						type: 'string',
						default: '',
						description:
							'A key of your own for this press. A press repeated with the same key and input within 24 hours returns the same run instead of starting another.',
					},
					{
						displayName: 'Max Price',
						name: 'maxPrice',
						type: 'number',
						default: 0,
						typeOptions: { minValue: 0, numberPrecision: 2 },
						description:
							"The most you will pay for this run, in Byssium. If the Widget's price has risen above it, nothing runs and nothing is charged.",
					},
				],
			},
		],
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const returnData: INodeExecutionData[] = [];
		for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
			try {
				const operation = this.getNodeParameter('operation', itemIndex) as string;
				const run: Run =
					operation === 'get'
						? await getRun(this, itemIndex, (this.getNodeParameter('runId', itemIndex) as string).trim())
						: await runWidget(
								this,
								itemIndex,
								(this.getNodeParameter('widgetId', itemIndex) as string).trim(),
								input(this, itemIndex),
								pressOptions(this, itemIndex),
							);
				const item: INodeExecutionData = { json: run, pairedItem: { item: itemIndex } };
				if (this.getNodeParameter('downloadOutputFiles', itemIndex, false) as boolean) {
					item.binary = await downloadOutputFiles(this, itemIndex, run);
				}
				returnData.push(item);
			} catch (error) {
				if (this.continueOnFail()) {
					returnData.push({ json: { error: (error as Error).message }, pairedItem: { item: itemIndex } });
					continue;
				}
				throw error instanceof NodeApiError ? error : new NodeOperationError(this.getNode(), error as Error, { itemIndex });
			}
		}
		return [returnData];
	}
}

/** The Widget's input: a JSON object of its fields by name, whose names are sent as they are. */
function input(ctx: IExecuteFunctions, itemIndex: number): IDataObject {
	const raw = ctx.getNodeParameter('input', itemIndex, '{}') as unknown;
	const value =
		typeof raw === 'string'
			? jsonParse<unknown>(raw.trim() === '' ? '{}' : raw, { fallbackValue: null })
			: raw;
	if (typeof value !== 'object' || value === null || Array.isArray(value)) {
		throw new NodeOperationError(ctx.getNode(), "Input must be a JSON object of the Widget's fields by name.", {
			itemIndex,
		});
	}
	return value as IDataObject;
}

function pressOptions(ctx: IExecuteFunctions, itemIndex: number): PressOptions {
	const options = ctx.getNodeParameter('options', itemIndex, {}) as { idempotencyKey?: string; maxPrice?: number };
	const press: PressOptions = { wait: ctx.getNodeParameter('waitForResult', itemIndex, true) as boolean };
	if (options.maxPrice !== undefined) press.maxPrice = options.maxPrice;
	if (options.idempotencyKey) press.idempotencyKey = options.idempotencyKey;
	return press;
}
