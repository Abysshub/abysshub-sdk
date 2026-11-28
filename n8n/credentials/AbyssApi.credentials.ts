import type { IAuthenticateGeneric, ICredentialTestRequest, ICredentialType, INodeProperties } from 'n8n-workflow';

export class AbyssApi implements ICredentialType {
	name = 'abyssApi';

	displayName = 'Abyss API';

	icon = 'file:../nodes/Abyss/abyss.svg' as const;

	documentationUrl = 'https://github.com/Abysshub/abysshub-sdk/tree/main/n8n#credentials';

	properties: INodeProperties[] = [
		{
			displayName: 'API Key',
			name: 'apiKey',
			type: 'string',
			typeOptions: { password: true },
			required: true,
			default: '',
			description: 'An API key from your Cave, starting with abyss_sk_',
		},
		{
			displayName: 'API URL',
			name: 'url',
			type: 'string',
			default: 'https://api.abysshub.com',
			description:
				'Where the Abyss API is. Keep the default: a key starting with abyss_sk_dev_ then goes to https://api.dev.abysshub.com. Any other URL is used as it is.',
		},
	];

	authenticate: IAuthenticateGeneric = {
		type: 'generic',
		properties: {
			headers: {
				Authorization: '=Bearer {{$credentials.apiKey}}',
			},
		},
	};

	test: ICredentialTestRequest = {
		request: {
			// The node's base-URL rule (nodes/Abyss/api.ts), as an expression.
			baseURL:
				'={{ ["", "https://api.abysshub.com"].includes(String($credentials.url || "").trim().replace(/\\/+$/, "")) ? (String($credentials.apiKey).startsWith("abyss_sk_dev_") ? "https://api.dev.abysshub.com" : "https://api.abysshub.com") : String($credentials.url).trim().replace(/\\/+$/, "") }}',
			url: '/v1/key',
		},
	};
}
