import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import App from '@/App';

const LIVENESS = { status: 'up', service: 'energy-transfer', version: '0.1.0' };

function stubFetch(implementation: () => Promise<unknown>) {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(implementation));
}

describe('App', () => {
  it('renders the project heading', () => {
    stubFetch(() => new Promise(() => {}));

    render(<App />);

    expect(
      screen.getByRole('heading', { name: /agentic p2p energy trading in microgrids/i }),
    ).toBeInTheDocument();
  });

  it('lists all seven measurable objectives', () => {
    stubFetch(() => new Promise(() => {}));

    render(<App />);

    for (const id of ['O1', 'O2', 'O3', 'O4', 'O5', 'O6', 'O7']) {
      expect(screen.getByText(id)).toBeInTheDocument();
    }
  });

  it('shows a checking state until the API answers', () => {
    stubFetch(() => new Promise(() => {}));

    render(<App />);

    expect(screen.getByRole('status')).toHaveTextContent(/checking api/i);
  });

  it('shows the service name and version once connected', async () => {
    stubFetch(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(LIVENESS) }),
    );

    render(<App />);

    expect(await screen.findByText(/api connected/i)).toBeInTheDocument();
    expect(screen.getByText('energy-transfer')).toBeInTheDocument();
    expect(screen.getByText('0.1.0')).toBeInTheDocument();
  });

  it('reports the API as unreachable when the request fails', async () => {
    stubFetch(() => Promise.reject(new Error('Failed to fetch')));

    render(<App />);

    expect(await screen.findByText(/api unreachable/i)).toBeInTheDocument();
    expect(screen.getByText(/docker compose up/i)).toBeInTheDocument();
  });

  it('reports the API as unreachable on a non-2xx response', async () => {
    stubFetch(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }));

    render(<App />);

    expect(await screen.findByText(/failed with status 500/i)).toBeInTheDocument();
  });
});
