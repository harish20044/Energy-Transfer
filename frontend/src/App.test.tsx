import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from '@/App';

/** The shell probes the API on mount; keep that off the network in tests. */
function stubHealthyApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: 'up', service: 'energy-transfer', version: '0.1.0' }),
    }),
  );
}

describe('App shell', () => {
  beforeEach(() => {
    stubHealthyApi();
    window.history.pushState({}, '', '/');
  });

  it('lands on the dashboard', () => {
    render(<App />);

    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByText('Energy flow')).toBeInTheDocument();
    expect(screen.getByText('Saved today')).toBeInTheDocument();
  });

  it('shows every navigation destination in the sidebar', () => {
    render(<App />);

    const nav = within(screen.getByRole('navigation'));
    for (const label of ['Dashboard', 'Live market', 'Grid network', 'Trades', 'Settings']) {
      expect(nav.getByRole('link', { name: label })).toBeInTheDocument();
    }
  });

  it('marks the current destination as active', () => {
    render(<App />);

    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
    expect(nav.getByRole('link', { name: 'Trades' })).not.toHaveAttribute('aria-current');
  });

  it('reports the backend as live once it answers', async () => {
    render(<App />);

    expect(await screen.findByText('Live')).toBeInTheDocument();
  });

  it('reports the backend as offline when it cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connection refused')));

    render(<App />);

    expect(await screen.findByText('Offline')).toBeInTheDocument();
  });
});

describe('navigation', () => {
  beforeEach(() => {
    stubHealthyApi();
    window.history.pushState({}, '', '/');
  });

  it('opens the live market', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Live market' }),
    );

    expect(screen.getByText('Order book')).toBeInTheDocument();
    expect(screen.getByText('Supply and demand')).toBeInTheDocument();
  });

  it('opens the grid network', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Grid network' }),
    );

    expect(screen.getByText('Feeder topology')).toBeInTheDocument();
    expect(screen.getByText('Constraint watch')).toBeInTheDocument();
  });

  it('opens trades and shows the decision record for the selected trade', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(within(screen.getByRole('navigation')).getByRole('link', { name: 'Trades' }));

    expect(screen.getByText('Decision record')).toBeInTheDocument();
    expect(screen.getByText('Why your agent did this')).toBeInTheDocument();
  });

  it('switches the decision record when another trade is selected', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(within(screen.getByRole('navigation')).getByRole('link', { name: 'Trades' }));
    await user.click(screen.getByRole('button', { name: /Bought from House 05/ }));

    expect(screen.getByRole('heading', { name: 'Bought from House 05' })).toBeInTheDocument();
    expect(screen.getByText('Cheaper than retail by')).toBeInTheDocument();
  });

  it('opens settings', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Settings' }),
    );

    expect(screen.getByText('Battery policy')).toBeInTheDocument();
    expect(screen.getByText('Market rules')).toBeInTheDocument();
  });
});
