import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from '@/App';

const FAKE_USER = {
  id: 'a1b2c3d4-0000-0000-0000-000000000000',
  email: 'harish@example.com',
  display_name: 'Harish P',
  role: 'household',
};

function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 400, status, json: () => Promise.resolve(body) };
}

/** Routes fetch by URL so a single mock can serve health checks, auth checks,
 *  and login — mirroring what the real app actually calls in one render. */
function stubApi({ authenticated = true, loginSucceeds = true } = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes('/health/live')) {
        return Promise.resolve(
          jsonResponse({ status: 'up', service: 'energy-transfer', version: '0.1.0' }),
        );
      }
      if (url.includes('/auth/me')) {
        return authenticated
          ? Promise.resolve(jsonResponse(FAKE_USER))
          : Promise.resolve(jsonResponse({ detail: 'Could not validate credentials' }, 401));
      }
      if (url.includes('/auth/login')) {
        return loginSucceeds
          ? Promise.resolve(
              jsonResponse({
                access_token: 'fake.access',
                refresh_token: 'fake.refresh',
                token_type: 'bearer',
              }),
            )
          : Promise.resolve(jsonResponse({ detail: 'Incorrect email or password' }, 401));
      }
      return Promise.resolve(jsonResponse({}, 404));
    }),
  );
}

/** Puts the app in the "already signed in" state a real reload would find. */
function signInAsFakeUser() {
  localStorage.setItem('energy-transfer.access_token', 'fake.access');
  localStorage.setItem('energy-transfer.refresh_token', 'fake.refresh');
}

beforeEach(() => {
  localStorage.clear();
  window.history.pushState({}, '', '/');
});

describe('unauthenticated visitor', () => {
  it('is redirected from the dashboard to the login page', async () => {
    stubApi({ authenticated: false });

    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('signs in and lands on the dashboard', async () => {
    stubApi({ authenticated: true });
    const user = userEvent.setup();

    render(<App />);

    await screen.findByRole('heading', { name: 'Sign in' });
    await user.type(screen.getByLabelText('Email'), 'harish@example.com');
    await user.type(screen.getByLabelText('Password'), 'correcthorsebattery');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(localStorage.getItem('energy-transfer.access_token')).toBe('fake.access');
  });

  it('shows the server error message on a failed login', async () => {
    stubApi({ authenticated: false, loginSucceeds: false });
    const user = userEvent.setup();

    render(<App />);

    await screen.findByRole('heading', { name: 'Sign in' });
    await user.type(screen.getByLabelText('Email'), 'harish@example.com');
    await user.type(screen.getByLabelText('Password'), 'wrongpassword');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect email or password/i);
  });
});

describe('authenticated session', () => {
  beforeEach(() => {
    signInAsFakeUser();
    stubApi({ authenticated: true });
  });

  it('lands on the dashboard', async () => {
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByText('Energy flow')).toBeInTheDocument();
    expect(screen.getByText('Saved today')).toBeInTheDocument();
  });

  it('shows the signed-in user in the sidebar', async () => {
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    expect(screen.getByText('Harish P')).toBeInTheDocument();
    expect(screen.getByText('household')).toBeInTheDocument();
  });

  it('signs out back to the login page', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(screen.getByRole('button', { name: /sign out/i }));

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(localStorage.getItem('energy-transfer.access_token')).toBeNull();
  });

  it('shows every navigation destination in the sidebar', async () => {
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    const nav = within(screen.getByRole('navigation'));
    for (const label of ['Dashboard', 'Live market', 'Grid network', 'Trades', 'Settings']) {
      expect(nav.getByRole('link', { name: label })).toBeInTheDocument();
    }
  });

  it('marks the current destination as active', async () => {
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    const nav = within(screen.getByRole('navigation'));
    expect(nav.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
    expect(nav.getByRole('link', { name: 'Trades' })).not.toHaveAttribute('aria-current');
  });

  it('reports the backend as live once it answers', async () => {
    render(<App />);

    expect(await screen.findByText('Live')).toBeInTheDocument();
  });
});

describe('navigation', () => {
  beforeEach(() => {
    signInAsFakeUser();
    stubApi({ authenticated: true });
  });

  it('opens the live market', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Live market' }),
    );

    expect(screen.getByText('Order book')).toBeInTheDocument();
    expect(screen.getByText('Supply and demand')).toBeInTheDocument();
  });

  it('opens the grid network', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Grid network' }),
    );

    expect(screen.getByText('Feeder topology')).toBeInTheDocument();
    expect(screen.getByText('Constraint watch')).toBeInTheDocument();
  });

  it('opens trades and shows the decision record for the selected trade', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(within(screen.getByRole('navigation')).getByRole('link', { name: 'Trades' }));

    expect(screen.getByText('Decision record')).toBeInTheDocument();
    expect(screen.getByText('Why your agent did this')).toBeInTheDocument();
  });

  it('switches the decision record when another trade is selected', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(within(screen.getByRole('navigation')).getByRole('link', { name: 'Trades' }));
    await user.click(screen.getByRole('button', { name: /Bought from House 05/ }));

    expect(screen.getByRole('heading', { name: 'Bought from House 05' })).toBeInTheDocument();
    expect(screen.getByText('Cheaper than retail by')).toBeInTheDocument();
  });

  it('opens settings', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Settings' }),
    );

    expect(screen.getByText('Battery policy')).toBeInTheDocument();
    expect(screen.getByText('Market rules')).toBeInTheDocument();
  });
});
