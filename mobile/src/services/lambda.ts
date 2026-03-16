import 'react-native-get-random-values';
import { LambdaClient, InvokeCommand } from '@aws-sdk/client-lambda';

const REGION = process.env.EXPO_PUBLIC_AWS_REGION || 'us-east-1';
const ACCESS_KEY = process.env.EXPO_PUBLIC_AWS_ACCESS_KEY_ID || '';
const SECRET_KEY = process.env.EXPO_PUBLIC_AWS_SECRET_ACCESS_KEY || '';
const LAMBDA_BASE_ARN = process.env.EXPO_PUBLIC_LAMBDA_BASE_ARN || '';

const client = new LambdaClient({
  region: REGION,
  credentials: {
    accessKeyId: ACCESS_KEY,
    secretAccessKey: SECRET_KEY,
  },
});

function parseOuterPayload(payload: Uint8Array | undefined): any {
  if (!payload) return {};
  const text = new TextDecoder().decode(payload);
  return JSON.parse(text);
}

function parseBody(outer: any): any {
  if (!outer) return null;
  return typeof outer.body === 'string' ? JSON.parse(outer.body) : (outer.body ?? outer);
}

export async function invokeLambda<T = any>(functionName: string, payload: any = {}): Promise<T> {
  const command = new InvokeCommand({
    FunctionName: LAMBDA_BASE_ARN + functionName,
    Payload: new TextEncoder().encode(JSON.stringify(payload)),
  });

  const response = await client.send(command);

  if (response.FunctionError) {
    const err = parseOuterPayload(response.Payload);
    throw new Error(err?.errorMessage || 'Lambda function error');
  }

  const outer = parseOuterPayload(response.Payload);
  const body = parseBody(outer) as T;

  if (typeof outer?.statusCode === 'number' && (outer.statusCode < 200 || outer.statusCode > 299)) {
    const msg = (body as any)?.message || `Lambda returned status ${outer.statusCode}`;
    throw new Error(msg);
  }

  return body;
}
