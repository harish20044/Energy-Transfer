import { describe, expect, it, vi } from 'vitest';

import { fetchLiveness } from '@/api/health';

describe('fetchLiveness', () => {
  it('returns the parsed body when the API responds 200', async () => {
    const body = { status: 'up', service: 'energy-transfer', version: '0.1.0' };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve(body) }),
    );

    await expect(fetchLiveness()).resolves.toEqual(body);
  });

  it('throws with the status code when the API responds with an error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: () => Promise.resolve({}) }),
    );

    await expect(fetchLiveness()).rejects.toThrow('failed with status 503');
  });

  it('forwards the abort signal so an unmount cancels the request', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) });
    vi.stubGlobal('fetch', fetchMock);

    const controller = new AbortController();
    await fetchLiveness(controller.signal);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/health/live'),
      expect.objectContaining({ signal: controller.signal }),
    );
  });
});
