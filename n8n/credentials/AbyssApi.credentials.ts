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
			description: 'Where the Abyss API is. Keep the default, or use https://api.dev.abysshub.com with a key starting with abyss_sk_dev_.',
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
			baseURL: '={{$credentials.url}}',
			url: '/v1/key',
		},
	};
}
