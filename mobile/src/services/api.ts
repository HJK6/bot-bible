import { fetchAuthSession } from 'aws-amplify/auth';

const API_URL = process.env.EXPO_PUBLIC_API_URL || '';

async function getAuthToken(): Promise<string> {
  const session = await fetchAuthSession();
  return session.tokens?.idToken?.toString() || '';
}

export async function callApi<T = any>(endpoint: string, payload: any = {}): Promise<T> {
  const token = await getAuthToken();
  const response = await fetch(`${API_URL}/${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': token,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || `API error: ${response.status}`);
  }

  return response.json();
}
