/** Client for the backend's registration, login, refresh and profile endpoints. */

import { API_BASE_URL, ApiError } from '@/api/client';

export { ApiError };

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export type UserRole = 'household' | 'operator' | 'admin';

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  household_id: string | null;
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body !== null && typeof body === 'object' && 'detail' in body) {
      const { detail } = body as { detail: unknown };
      if (typeof detail === 'string') return detail;
    }
  } catch {
    // Response body wasn't JSON — fall through to the generic message.
  }
  return `Request failed with status ${response.status}`;
}

export async function register(input: {
  email: string;
  password: string;
  displayName: string;
}): Promise<UserProfile> {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: input.email,
      password: input.password,
      display_name: input.displayName,
    }),
  });
  if (!response.ok) throw new ApiError(await readErrorDetail(response), response.status);
  return (await response.json()) as UserProfile;
}

export async function login(input: { email: string; password: string }): Promise<TokenPair> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new ApiError(await readErrorDetail(response), response.status);
  return (await response.json()) as TokenPair;
}

export async function refresh(refreshToken: string): Promise<TokenPair> {
  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) throw new ApiError(await readErrorDetail(response), response.status);
  return (await response.json()) as TokenPair;
}

export async function fetchMe(accessToken: string): Promise<UserProfile> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) throw new ApiError(await readErrorDetail(response), response.status);
  return (await response.json()) as UserProfile;
}
