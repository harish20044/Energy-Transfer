import { useEffect, useState } from 'react';

import { fetchLiveness } from '@/api/health';

export type ApiHealth = 'checking' | 'online' | 'offline';

/**
 * Whether the backend is reachable.
 *
 * The dashboard renders from mock data today, so a dead API degrades the status
 * dot and nothing else — the page stays useful either way.
 */
export function useApiHealth(): ApiHealth {
  const [status, setStatus] = useState<ApiHealth>('checking');

  useEffect(() => {
    const controller = new AbortController();

    fetchLiveness(controller.signal)
      .then(() => {
        setStatus('online');
      })
      .catch(() => {
        // An abort is teardown, not a failure worth showing.
        if (!controller.signal.aborted) setStatus('offline');
      });

    return () => {
      controller.abort();
    };
  }, []);

  return status;
}
