import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import App from '@/App';

const FAKE_USER = {
  id: 'a1b2c3d4-0000-0000-0000-000000000000',
  email: 'harish@example.com',
  display_name: 'Harish P',
  role: 'household',
  household_id: 'h1',
};

const FAKE_HOUSEHOLD = {
  id: 'h1',
  display_name: 'House 1',
  member_count: 4,
  solar_capacity_kwp: 5.0,
  battery_capacity_kwh: 10.0,
  battery_max_charge_kw: 3.0,
  battery_max_discharge_kw: 3.0,
  evening_reserve: 0.4,
};

const FAKE_SIMULATION = {
  tick_index: 10,
  running: false,
  scenario: 'clear',
  seconds_per_tick: 2,
  simulated_day: 0,
  simulated_hour: 2.5,
  tick_minutes: 15,
  updated_at: '2026-01-01T00:00:00Z',
};

const FAKE_READINGS = [
  {
    tick_index: 10,
    consumption_kw: 0.8,
    generation_kw: 2.1,
    battery_soc: 0.6,
    battery_action: 'charging',
    grid_kwh: 0,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    tick_index: 9,
    consumption_kw: 0.7,
    generation_kw: 1.9,
    battery_soc: 0.58,
    battery_action: 'charging',
    grid_kwh: 0,
    created_at: '2026-01-01T00:00:00Z',
  },
];

// h1 is the seller on one and the buyer on the other, so the dashboard shows
// both a "Sold to" and a "Bought from" line from a single fixture.
const FAKE_OWN_TRADES = [
  {
    tick_index: 10,
    round_index: 1,
    buyer_household_id: 'h2',
    seller_household_id: 'h1',
    kwh: 0.3,
    price_per_kwh: 5.4,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    tick_index: 8,
    round_index: 0,
    buyer_household_id: 'h1',
    seller_household_id: 'h5',
    kwh: 0.4,
    price_per_kwh: 4.1,
    created_at: '2026-01-01T00:00:00Z',
  },
];

const FAKE_BALANCE = { household_id: 'h1', net_balance: 12.5, total_sold_kwh: 3.2, total_bought_kwh: 1.1 };

const FAKE_NEGOTIATION = {
  tick_index: 9,
  rounds: [
    {
      round_index: 0,
      asks: [{ household_id: 'h1', side: 'ask', price: 8.0, kwh: 0.3 }],
      bids: [{ household_id: 'h2', side: 'bid', price: 3.0, kwh: 0.3 }],
      trades: [],
    },
    {
      round_index: 1,
      asks: [{ household_id: 'h1', side: 'ask', price: 5.5, kwh: 0.3 }],
      bids: [{ household_id: 'h2', side: 'bid', price: 5.6, kwh: 0.3 }],
      trades: [
        {
          tick_index: 9,
          round_index: 1,
          buyer_household_id: 'h2',
          seller_household_id: 'h1',
          kwh: 0.3,
          price_per_kwh: 5.55,
          created_at: '2026-01-01T00:00:00Z',
        },
      ],
    },
  ],
};

const FAKE_NETWORK = {
  household_ids: ['h1', 'h2', 'h3'],
  lines: [
    { id: 'substation->h1', from_bus: 'substation', to_bus: 'h1', thermal_limit_kw: 20 },
    { id: 'substation->h2', from_bus: 'substation', to_bus: 'h2', thermal_limit_kw: 20 },
    { id: 'substation->h3', from_bus: 'substation', to_bus: 'h3', thermal_limit_kw: 20 },
  ],
};

function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 400, status, json: () => Promise.resolve(body) };
}

/** Routes fetch by URL so a single mock can serve every endpoint the live
 *  app actually calls in one render — auth, the household's own live data,
 *  and the shared market/feeder data. */
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
      if (url.includes('/households/me/evening-reserve')) {
        return Promise.resolve(jsonResponse(FAKE_HOUSEHOLD));
      }
      if (url.includes('/households/me/readings')) {
        return Promise.resolve(jsonResponse(FAKE_READINGS));
      }
      if (url.includes('/households/me/trades')) {
        return Promise.resolve(jsonResponse(FAKE_OWN_TRADES));
      }
      if (url.includes('/households/me/balance')) {
        return Promise.resolve(jsonResponse(FAKE_BALANCE));
      }
      if (url.includes('/households/me')) {
        return Promise.resolve(jsonResponse(FAKE_HOUSEHOLD));
      }
      if (url.includes('/simulation/state')) {
        return Promise.resolve(jsonResponse(FAKE_SIMULATION));
      }
      if (url.includes('/simulation/negotiation')) {
        return Promise.resolve(jsonResponse(FAKE_NEGOTIATION));
      }
      if (url.includes('/simulation/trades')) {
        return Promise.resolve(jsonResponse(FAKE_NEGOTIATION.rounds[1]?.trades ?? []));
      }
      if (url.includes('/simulation/curtailments')) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.includes('/simulation/network')) {
        return Promise.resolve(jsonResponse(FAKE_NETWORK));
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

  it('lands on the dashboard with this household’s own live data', async () => {
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByText('Energy flow')).toBeInTheDocument();
    expect(await screen.findByText('Net balance')).toBeInTheDocument();
    expect(await screen.findByText('Sold to House 2')).toBeInTheDocument();
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

  it('opens the live market and shows the negotiation replay', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Live market' }),
    );

    expect(await screen.findByText('Watch them negotiate')).toBeInTheDocument();
    expect(screen.getByText('Recent clearing prices')).toBeInTheDocument();
  });

  it('opens the grid network', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Grid network' }),
    );

    expect(await screen.findByText('Feeder topology')).toBeInTheDocument();
    expect(screen.getByText('Constraint watch')).toBeInTheDocument();
  });

  it('opens trades and shows the decision record for the selected trade', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(within(screen.getByRole('navigation')).getByRole('link', { name: 'Trades' }));

    expect(await screen.findByText('Decision record')).toBeInTheDocument();
    expect(screen.getByText('Why your agent did this')).toBeInTheDocument();
  });

  it('switches the decision record when another trade is selected', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(within(screen.getByRole('navigation')).getByRole('link', { name: 'Trades' }));
    await user.click(await screen.findByRole('button', { name: /Bought from House 5/ }));

    expect(screen.getByRole('heading', { name: 'Bought from House 5' })).toBeInTheDocument();
    expect(screen.getByText('Cheaper than retail by')).toBeInTheDocument();
  });

  it('opens settings', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Settings' }),
    );

    expect(await screen.findByText('Battery policy')).toBeInTheDocument();
    expect(screen.getByText('Market rules')).toBeInTheDocument();
  });
});
