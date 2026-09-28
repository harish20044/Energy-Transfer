/** Shared plumbing for every authenticated backend call: one place that
 *  attaches the bearer token and turns a non-2xx response into an error. */

import { API_BASE_URL } from '@/api/health';

export { API_BASE_URL };

/** Raised for any non-2xx response, carrying the API's own detail message
 *  (FastAPI/Pydantic put the human-readable reason there). */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
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

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal | undefined;
}

/** Every household- or simulation-scoped call goes through here. The token
 *  is always passed explicitly rather than read from storage internally, so
 *  a component's data-fetching is testable without touching localStorage. */
export async function apiFetch<T>(
  path: string,
  accessToken: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : null,
    signal: options.signal ?? null,
  });
  if (!response.ok) throw new ApiError(await readErrorDetail(response), response.status);
  return (await response.json()) as T;
}
