/** Client for the backend health endpoints. */

export interface LivenessResponse {
  status: string;
  service: string;
  version: string;
}

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';

/**
 * Ask the API whether it is alive.
 *
 * @param signal - Aborts the request when the caller unmounts, so a slow
 *                 response cannot update a component that is already gone.
 * @throws Error when the API responds with a non-2xx status.
 */
export async function fetchLiveness(signal?: AbortSignal): Promise<LivenessResponse> {
  // RequestInit.signal is `AbortSignal | null`, so an absent signal must be
  // normalised to null rather than left undefined.
  const response = await fetch(`${API_BASE_URL}/health/live`, { signal: signal ?? null });

  if (!response.ok) {
    throw new Error(`API health check failed with status ${response.status}`);
  }

  return (await response.json()) as LivenessResponse;
}
