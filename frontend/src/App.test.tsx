import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

const WEATHER = {
  date: '2026-05-15',
  sky: 'clear',
  t_max_c: 38.1,
  t_min_c: 27.2,
  temperature_now_c: 36.4,
  sunrise_h: 5.72,
  sunset_h: 18.44,
};

function sessionState(status: string, hoursDelivered: number) {
  return {
    status,
    sim_date: '2026-05-15',
    start_hour: 14,
    horizon_hours: 2,
    scenario: 'auto',
    tick_minutes: 15,
    hours_delivered: hoursDelivered,
    clock_hours: 14 + hoursDelivered,
    retail_tariff: 10.5,
    feed_in_tariff: 3.61,
    peak_surcharge_pct: 0,
    power_cut: null,
    weather: WEATHER,
    households:
      status === 'setup'
        ? []
        : [
            {
              household_id: 'h1',
              display_name: 'House 1',
              start_soc: 1.0,
              guests: 0,
              away_from: null,
              away_to: null,
              work_from_home: false,
              panel_derate: 0,
              battery_capacity_kwh: 10,
            },
          ],
  };
}

const DECISION = {
  household_id: 'h1',
  display_name: 'House 1',
  strategy: 'sell-surplus',
  side: 'sell',
  firm: true,
  quantity_kwh: 1.5,
  limit_price: 3.61,
  opening_price: 4.87,
  message: '2 pm–3 pm: offering 1.50 units — the panels should out-produce our load.',
  outcome: 'Sold 1.20 units to House 3 at ₹6.40 (round 2).',
  reasons: ['Forecast load 0.4–0.8 kW (P10–P90)'],
};

function ownSlot(slot: number, delivered: boolean) {
  return {
    slot,
    hour_of_day: 14 + slot,
    forecast: {
      slot,
      day: '2026-05-15',
      hour_of_day: 14 + slot,
      consumption_p10: 0.4,
      consumption_p50: 0.6,
      consumption_p90: 0.8,
      generation_p10: 2.0,
      generation_p50: 2.4,
      generation_p90: 2.8,
    },
    p2p_sold_kwh: slot === 0 ? 1.2 : 0,
    p2p_bought_kwh: 0,
    eb_bought_kwh: 0,
    eb_sold_kwh: slot === 0 ? 0.3 : 0,
    retail_tariff: 10.5,
    feed_in_tariff: 3.61,
    eb_available: true,
    decision: slot === 0 ? DECISION : null,
    delivered,
    actual_consumption_kwh: delivered ? 0.55 : null,
    actual_generation_kwh: delivered ? 2.3 : null,
    actual_eb_import_kwh: delivered ? 0 : null,
    actual_eb_export_kwh: delivered ? 0.4 : null,
    actual_unserved_kwh: delivered ? 0 : null,
    battery_soc_end: delivered ? 1.0 : null,
  };
}

const STATEMENT = {
  basis: 'planned',
  hours: 2,
  earned_from_neighbours_inr: 7.68,
  paid_to_neighbours_inr: 0,
  paid_to_eb_inr: 0,
  earned_from_eb_inr: 1.08,
  eb_only_paid_inr: 0,
  eb_only_earned_inr: 5.42,
  saved_vs_eb_only_inr: 3.34,
  units_sold_to_neighbours: 1.2,
  units_bought_from_neighbours: 0,
  units_from_eb: 0,
  units_to_eb: 0.3,
  units_unserved: 0,
};

function ownSession(hoursDelivered: number) {
  return {
    household_id: 'h1',
    model: 'lightgbm-quantile',
    slots: [ownSlot(0, hoursDelivered > 0), ownSlot(1, hoursDelivered > 1)],
    planned: STATEMENT,
    delivered:
      hoursDelivered > 0 ? { ...STATEMENT, basis: 'delivered', hours: hoursDelivered } : null,
  };
}

const OVERVIEW = [0, 1].map((slot) => ({
  slot,
  day: '2026-05-15',
  hour_of_day: 14 + slot,
  retail_tariff: 10.5,
  feed_in_tariff: 3.61,
  eb_available: true,
  forecast_need_kwh: 1.4,
  forecast_spare_kwh: 7.1,
  p2p_kwh: 1.2,
  p2p_avg_price: 6.4,
  eb_bought_kwh: 0.2,
  eb_sold_kwh: 3.1,
  unserved_kwh: 0,
  delivered: false,
  actual_consumption_kwh: null,
  actual_generation_kwh: null,
}));

const SLOT_MARKET = {
  slot: 0,
  hour_of_day: 14,
  retail_tariff: 10.5,
  feed_in_tariff: 3.61,
  eb_available: true,
  rounds: [
    {
      round_index: 0,
      asks: [{ household_id: 'h1', side: 'ask', price: 4.87, kwh: 1.5 }],
      bids: [{ household_id: 'h3', side: 'bid', price: 6.9, kwh: 1.2 }],
      trades: [
        {
          buyer_household_id: 'h3',
          seller_household_id: 'h1',
          kwh: 1.2,
          price_per_kwh: 6.4,
          round_index: 0,
        },
      ],
    },
  ],
  eb_flows: [{ household_id: 'h1', side: 'ask', kwh: 0.3, price: 3.61 }],
  agents: [
    DECISION,
    {
      ...DECISION,
      household_id: 'h3',
      display_name: 'House 3',
      strategy: 'buy-shortfall',
      side: 'buy',
      message: '2 pm–3 pm: need 1.20 units — no panels on this roof.',
      outcome: 'Bought 1.20 units from House 1 at ₹6.40 (round 1).',
    },
  ],
};

const FAKE_FAMILY = {
  house: { bedrooms: 4, washrooms: 5, halls: 1, ac_units: 4 },
  members: [
    {
      index: 0,
      age: 42,
      role: 'parent',
      occupation: 'office',
      room: 1,
      status: 'away',
      home_now: false,
    },
    {
      index: 1,
      age: 39,
      role: 'parent',
      occupation: 'homemaker',
      room: 1,
      status: 'home',
      home_now: true,
    },
    {
      index: 2,
      age: 68,
      role: 'grandparent',
      occupation: 'retired',
      room: 2,
      status: 'asleep',
      home_now: true,
    },
  ],
  rooms: [
    { room: 1, occupied: false, ac_on: false, ac_kw: 0, ac_intensity: 0 },
    { room: 2, occupied: true, ac_on: true, ac_kw: 1.2, ac_intensity: 0.8 },
    { room: 3, occupied: false, ac_on: false, ac_kw: 0, ac_intensity: 0 },
    { room: 4, occupied: false, ac_on: false, ac_kw: 0, ac_intensity: 0 },
  ],
  appliance_kw: { cooling: 1.2, refrigerator: 0.06, fans: 0.12, ev: 0 },
};

const OWN_TRADES = [
  {
    tick_index: 0,
    round_index: 0,
    buyer_household_id: 'h3',
    seller_household_id: 'h1',
    kwh: 1.2,
    price_per_kwh: 6.4,
    created_at: '2026-01-01T00:00:00Z',
  },
];

OWN_TRADES.push({
  tick_index: 1,
  round_index: 1,
  buyer_household_id: 'h1',
  seller_household_id: 'h5',
  kwh: 0.4,
  price_per_kwh: 7.1,
  created_at: '2026-01-01T00:00:00Z',
});

const AGENT_MEMORY = {
  household_id: 'h1',
  sell_margin: 0.31,
  buy_margin: 0.28,
  price_by_hour: Array.from({ length: 24 }, (_, h) => (h === 14 ? 6.4 : null)),
  trades: 3,
  units_sold: 2.4,
  units_bought: 0.4,
  savings_inr: 12.5,
  graph_nodes: ['perceive', 'project', 'value', 'order', 'speak'],
};

const CURTAILMENTS = [
  {
    tick_index: 0,
    buyer_household_id: 'h3',
    seller_household_id: 'h1',
    curtailed_kwh: 0.2,
    reason: 'line substation->h3 thermal limit',
    created_at: '2026-01-01T00:00:00Z',
  },
];

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

interface StubOptions {
  authenticated?: boolean;
  loginSucceeds?: boolean;
  status?: 'setup' | 'planned';
  planFails?: boolean;
}

/** Routes fetch by URL (most specific first) so one mock serves every
 *  endpoint the app calls, and keeps a tiny session state machine so Next
 *  hour / Run to end / Predict & trade behave like the real backend. */
function stubApi({
  authenticated = true,
  loginSucceeds = true,
  status = 'planned',
  planFails = false,
}: StubOptions = {}) {
  let current: string = status;
  let delivered = 0;
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';

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
    if (url.includes('/session/plan')) {
      if (planFails) {
        return Promise.resolve(
          jsonResponse({ detail: 'the feed-in tariff must be below the retail tariff' }, 422),
        );
      }
      current = 'planned';
      delivered = 0;
      return Promise.resolve(jsonResponse(sessionState(current, delivered)));
    }
    if (url.includes('/session/next-hour')) {
      delivered = Math.min(2, delivered + 1);
      current = delivered >= 2 ? 'complete' : 'playing';
      return Promise.resolve(jsonResponse(sessionState(current, delivered)));
    }
    if (url.includes('/session/reset')) {
      current = 'setup';
      delivered = 0;
      return Promise.resolve(jsonResponse(sessionState(current, delivered)));
    }
    if (url.includes('/session/overview')) {
      return Promise.resolve(jsonResponse(current === 'setup' ? [] : OVERVIEW));
    }
    if (url.includes('/session/market')) {
      return Promise.resolve(jsonResponse(SLOT_MARKET));
    }
    if (url.includes('/households/me/session')) {
      return current === 'setup'
        ? Promise.resolve(
            jsonResponse({
              household_id: 'h1',
              model: 'lightgbm-quantile',
              slots: [],
              planned: null,
              delivered: null,
            }),
          )
        : Promise.resolve(jsonResponse(ownSession(delivered)));
    }
    if (url.includes('/session')) {
      return Promise.resolve(jsonResponse(sessionState(current, delivered)));
    }
    if (url.includes('/agents/me/chat')) {
      return Promise.resolve(
        jsonResponse({
          reply: 'I sold 1.20 units to House 3 at ₹6.40 because our panels were ahead of our load.',
          provider: 'stub',
          tools_used: ['get_my_plan'],
        }),
      );
    }
    if (url.includes('/agents/me')) {
      return Promise.resolve(jsonResponse(AGENT_MEMORY));
    }
    if (url.includes('/households/me/evening-reserve')) {
      return Promise.resolve(jsonResponse(FAKE_HOUSEHOLD));
    }
    if (url.includes('/households/me/readings')) {
      return Promise.resolve(jsonResponse([]));
    }
    if (url.includes('/households/me/trades')) {
      return Promise.resolve(jsonResponse(current === 'setup' ? [] : OWN_TRADES));
    }
    if (url.includes('/households/me/family')) {
      return Promise.resolve(jsonResponse(FAKE_FAMILY));
    }
    if (url.includes('/households/me')) {
      return Promise.resolve(jsonResponse(FAKE_HOUSEHOLD));
    }
    if (url.includes('/simulation/curtailments')) {
      return Promise.resolve(jsonResponse(current === 'setup' ? [] : CURTAILMENTS));
    }
    if (url.includes('/simulation/trades')) {
      return Promise.resolve(jsonResponse(OWN_TRADES));
    }
    if (url.includes('/simulation/network')) {
      return Promise.resolve(jsonResponse(FAKE_NETWORK));
    }
    return Promise.resolve(jsonResponse({ detail: `unmocked ${method} ${url}` }, 404));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function calls(fetchMock: ReturnType<typeof stubApi>, fragment: string, method = 'POST') {
  return fetchMock.mock.calls.filter(
    ([input, init]) =>
      String(input).includes(fragment) &&
      ((init as RequestInit | undefined)?.method ?? 'GET') === method,
  );
}

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
    stubApi();
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

describe('dashboard', () => {
  beforeEach(() => {
    signInAsFakeUser();
  });

  it('shows money as separate earned and paid cards, never a signed balance', async () => {
    stubApi();
    render(<App />);

    expect(await screen.findByText('Earned from neighbours')).toBeInTheDocument();
    expect(screen.getByText('Paid to neighbours')).toBeInTheDocument();
    expect(screen.getByText('Paid to the EB')).toBeInTheDocument();
    expect(screen.getByText('Earned from the EB')).toBeInTheDocument();
    expect(screen.getByText('Saved vs EB alone')).toBeInTheDocument();
    expect(screen.queryByText(/Net balance/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/-₹|−₹/)).not.toBeInTheDocument();
  });

  it("shows the agent's plan, the family and the forecast", async () => {
    stubApi();
    render(<App />);

    expect(await screen.findByText(/offering 1.50 units/)).toBeInTheDocument();
    expect(screen.getByText(/Sold 1.20 units to House 3/)).toBeInTheDocument();
    expect(await screen.findByText('Grandparent · 68y')).toBeInTheDocument();
    expect(screen.getByText('Forecast vs what happened')).toBeInTheDocument();
  });

  it('invites planning a session when none exists', async () => {
    stubApi({ status: 'setup' });
    render(<App />);

    expect(await screen.findByText('No session planned yet')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /plan a session/i }).length).toBeGreaterThan(0);
  });
});

describe('session controls', () => {
  beforeEach(() => {
    signInAsFakeUser();
  });

  it('Next hour delivers exactly one hour', async () => {
    const fetchMock = stubApi();
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole('button', { name: /next hour/i }));

    await waitFor(() => {
      expect(calls(fetchMock, '/session/next-hour')).toHaveLength(1);
    });
    expect(await screen.findByText('1/2 h')).toBeInTheDocument();
  });

  it('Run to end steps through every remaining hour and stops at the horizon', async () => {
    const fetchMock = stubApi();
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole('button', { name: /run to end/i }));

    expect(await screen.findByText('Session complete', {}, { timeout: 6000 })).toBeInTheDocument();
    expect(calls(fetchMock, '/session/next-hour')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /next hour/i })).not.toBeInTheDocument();
  });

  it('plans a new session from the setup page', async () => {
    const fetchMock = stubApi({ status: 'setup' });
    const user = userEvent.setup();
    render(<App />);

    const nav = within(await screen.findByRole('navigation'));
    await user.click(nav.getByRole('link', { name: 'Plan session' }));
    expect(await screen.findByText("Each household's what-ifs")).toBeInTheDocument();
    await screen.findByText('House 3');

    await user.click(screen.getByRole('button', { name: '24 h' }));
    await user.click(screen.getByRole('button', { name: /Heatwave/ }));
    await user.click(screen.getByRole('button', { name: 'Mixed neighbourhood' }));
    await user.click(screen.getByRole('button', { name: /predict & trade/i }));

    await waitFor(() => {
      expect(calls(fetchMock, '/session/plan')).toHaveLength(1);
    });
    const body = JSON.parse(
      String((calls(fetchMock, '/session/plan')[0]?.[1] as RequestInit).body),
    ) as {
      horizon_hours: number;
      scenario: string;
      households: {
        household_id: string;
        panel_derate: number;
        battery_capacity_kwh: number | null;
      }[];
    };
    expect(body.horizon_hours).toBe(24);
    expect(body.scenario).toBe('heatwave');
    expect(body.households.find((h) => h.household_id === 'h3')).toMatchObject({
      panel_derate: 1,
      battery_capacity_kwh: 0,
    });
    expect(
      await screen.findByRole('heading', { name: 'Dashboard' }, { timeout: 5000 }),
    ).toBeInTheDocument();
  }, 20_000);
});

describe('navigation', () => {
  beforeEach(() => {
    signInAsFakeUser();
  });

  it('shows every destination in the sidebar and marks the current one', async () => {
    stubApi();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    const nav = within(screen.getByRole('navigation'));
    for (const label of [
      'Dashboard',
      'Plan session',
      'Market',
      'Grid network',
      'Trades',
      'Settings',
    ]) {
      expect(nav.getByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(nav.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
  });

  it("opens the market with every agent's messages", async () => {
    stubApi();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(within(screen.getByRole('navigation')).getByRole('link', { name: 'Market' }));

    expect(await screen.findByText('What the agents said')).toBeInTheDocument();
    expect(await screen.findByText(/no panels on this roof/)).toBeInTheDocument();
    expect(screen.getByText('The EB covered the rest')).toBeInTheDocument();
  });

  it("opens trades with the agent's own reasoning", async () => {
    stubApi();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(within(screen.getByRole('navigation')).getByRole('link', { name: 'Trades' }));

    expect(await screen.findByText('Decision record')).toBeInTheDocument();
    expect(await screen.findByText('Why your agent did this')).toBeInTheDocument();
    expect(screen.getAllByText(/offering 1.50 units/).length).toBeGreaterThan(0);
  });

  it('opens the grid network and settings', async () => {
    stubApi();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard' });
    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Grid network' }),
    );
    expect(await screen.findByText('Feeder topology')).toBeInTheDocument();

    await user.click(
      within(screen.getByRole('navigation')).getByRole('link', { name: 'Settings' }),
    );
    expect(await screen.findByText('Battery reserve')).toBeInTheDocument();
  });

  it('reports the backend as live once it answers', async () => {
    stubApi();
    render(<App />);
    expect(await screen.findByText('Live')).toBeInTheDocument();
  });
});

describe('agent chat', () => {
  beforeEach(() => {
    signInAsFakeUser();
  });

  it('sends a question and shows the reply', async () => {
    const fetchMock = stubApi();
    const user = userEvent.setup();
    render(<App />);

    await user.type(
      await screen.findByLabelText('Message your agent'),
      'Why did you sell at 2 pm?',
    );
    await user.click(screen.getByRole('button', { name: 'Send' }));

    expect(
      await screen.findByText(/because our panels were ahead of our load/),
    ).toBeInTheDocument();
    expect(calls(fetchMock, '/agents/me/chat')).toHaveLength(1);
  });
});

describe('interactions', () => {
  beforeEach(() => {
    signInAsFakeUser();
  });

  it('every what-if on the plan page reaches the request', async () => {
    const fetchMock = stubApi({ status: 'setup' });
    const user = userEvent.setup();
    window.history.pushState({}, '', '/session');
    render(<App />);

    await screen.findByText('House 2');
    fireEvent.change(screen.getByLabelText(/^Date/), { target: { value: '2026-01-20' } });
    await user.selectOptions(screen.getByLabelText('Start time'), '16');
    await user.click(screen.getByRole('button', { name: '8 h' }));
    await user.click(screen.getByRole('button', { name: /Monsoon rain/ }));
    fireEvent.change(screen.getByLabelText(/EB charges/), { target: { value: '11.55' } });
    fireEvent.change(screen.getByLabelText(/EB pays/), { target: { value: '3.5' } });
    fireEvent.change(screen.getByLabelText(/Evening peak surcharge/), { target: { value: '20' } });
    await user.click(screen.getByRole('button', { name: 'Evening power cut' }));
    await user.selectOptions(screen.getByLabelText('Power cut from'), '20');
    await user.selectOptions(screen.getByLabelText('Power cut to'), '22');

    await user.selectOptions(screen.getByLabelText('House 2 guests'), '2');
    await user.click(screen.getByLabelText('House 2 family out'));
    await user.selectOptions(screen.getByLabelText('House 2 out from'), '18');
    await user.selectOptions(screen.getByLabelText('House 2 out until'), '23');
    await user.click(screen.getByLabelText('House 2 works from home'));
    await user.selectOptions(screen.getByLabelText('House 2 panels'), '0.4');
    await user.selectOptions(screen.getByLabelText('House 2 battery'), '5');
    await user.selectOptions(screen.getByLabelText('House 2 starting charge'), '0.25');
    await user.click(screen.getByRole('button', { name: /predict & trade/i }));

    await waitFor(() => {
      expect(calls(fetchMock, '/session/plan')).toHaveLength(1);
    });
    const body = JSON.parse(
      String((calls(fetchMock, '/session/plan')[0]?.[1] as RequestInit).body),
    ) as Record<string, unknown> & { households: Record<string, unknown>[] };
    expect(body).toMatchObject({
      sim_date: '2026-01-20',
      start_hour: 16,
      horizon_hours: 8,
      scenario: 'rainy',
      power_cut: { start_hour: 20, end_hour: 22 },
      tariffs: { retail_tariff: 11.55, feed_in_tariff: 3.5, peak_surcharge_pct: 20 },
    });
    expect(body.households.find((h) => h.household_id === 'h2')).toEqual({
      household_id: 'h2',
      guests: 2,
      away_from: 18,
      away_to: 23,
      work_from_home: true,
      panel_derate: 0.4,
      battery_capacity_kwh: 5,
      battery_start_soc: 0.25,
    });
  }, 30_000);

  it('the identical-homes preset clears every what-if', async () => {
    const fetchMock = stubApi({ status: 'setup' });
    const user = userEvent.setup();
    window.history.pushState({}, '', '/session');
    render(<App />);

    await screen.findByText('House 3');
    await user.click(screen.getByRole('button', { name: 'Mixed neighbourhood' }));
    await user.click(screen.getByRole('button', { name: 'Identical homes' }));
    await user.click(screen.getByRole('button', { name: /predict & trade/i }));

    await waitFor(() => {
      expect(calls(fetchMock, '/session/plan')).toHaveLength(1);
    });
    const body = JSON.parse(
      String((calls(fetchMock, '/session/plan')[0]?.[1] as RequestInit).body),
    ) as { households: { panel_derate: number }[]; power_cut: unknown };
    expect(body.households.every((h) => h.panel_derate === 0)).toBe(true);
    expect(body.power_cut).toBeNull();
  }, 20_000);

  it('a rejected plan shows why and stays on the page', async () => {
    stubApi({ status: 'setup', planFails: true });
    const user = userEvent.setup();
    window.history.pushState({}, '', '/session');
    render(<App />);

    await screen.findByText('House 3');
    await user.click(screen.getByRole('button', { name: /predict & trade/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/feed-in tariff must be below/);
    expect(screen.getByText("Each household's what-ifs")).toBeInTheDocument();
  });

  it('Stop halts Run to end after the hour in progress', async () => {
    const fetchMock = stubApi();
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole('button', { name: /run to end/i }));
    await user.click(await screen.findByRole('button', { name: /stop/i }));

    expect(
      await screen.findByRole('button', { name: /run to end/i }, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(calls(fetchMock, '/session/next-hour')).toHaveLength(1);
  });

  it("the market's round and hour pickers load what was asked for", async () => {
    const fetchMock = stubApi();
    const user = userEvent.setup();
    window.history.pushState({}, '', '/market');
    render(<App />);

    await user.click(await screen.findByRole('button', { name: /Round 1/ }));
    expect(screen.getByText('Matched this round')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '3 pm' }));
    await waitFor(() => {
      expect(calls(fetchMock, '/session/market?slot=1', 'GET').length).toBeGreaterThan(0);
    });
  });

  it('selecting a purchase shows its own decision record', async () => {
    stubApi();
    const user = userEvent.setup();
    window.history.pushState({}, '', '/trades');
    render(<App />);

    await user.click(await screen.findByRole('button', { name: /Bought from House 5/ }));
    expect(screen.getByRole('heading', { name: 'Bought from House 5' })).toBeInTheDocument();
    expect(screen.getByText(/Cheaper than the EB/)).toBeInTheDocument();
  });

  it('settings show what the agent learned, and the reserve slider saves', async () => {
    const fetchMock = stubApi();
    window.history.pushState({}, '', '/settings');
    render(<App />);

    expect(await screen.findByText('What your agent has learned')).toBeInTheDocument();
    expect(await screen.findByText('₹6.4')).toBeInTheDocument();
    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '60' } });
    fireEvent.mouseUp(slider, { target: { value: '60' } });

    await waitFor(() => {
      expect(calls(fetchMock, '/households/me/evening-reserve', 'PATCH')).toHaveLength(1);
    });
  });

  it('the network flags households the safety layer curtailed', async () => {
    stubApi();
    window.history.pushState({}, '', '/network');
    render(<App />);

    expect(await screen.findByText(/thermal limit, 2 pm/)).toBeInTheDocument();
  });
});
