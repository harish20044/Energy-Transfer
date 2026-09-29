/** Client for planning sessions: set one up with its what-ifs, let every
 *  household's agent trade the hours ahead, then deliver them one at a time.
 *  Nothing runs on its own — every step here is an explicit request. */

import { apiFetch } from '@/api/client';

export type Scenario = 'auto' | 'clear' | 'cloudy' | 'rainy' | 'heatwave';
export type SessionStatus = 'setup' | 'planned' | 'playing' | 'complete';
export type Horizon = 4 | 8 | 12 | 24;
export type Sky = 'clear' | 'partly cloudy' | 'overcast' | 'rain';

export interface HouseholdWhatIf {
  household_id: string;
  guests?: number;
  away_from?: number | null;
  away_to?: number | null;
  work_from_home?: boolean;
  panel_derate?: number;
  battery_capacity_kwh?: number | null;
  battery_start_soc?: number | null;
}

export interface PowerCut {
  start_hour: number;
  end_hour: number;
}

export interface TariffWhatIf {
  retail_tariff?: number | null;
  feed_in_tariff?: number | null;
  peak_surcharge_pct?: number;
}

export interface SessionConfig {
  sim_date: string;
  start_hour: number;
  horizon_hours: Horizon;
  scenario: Scenario;
  households: HouseholdWhatIf[];
  power_cut: PowerCut | null;
  tariffs: TariffWhatIf;
}

export interface Weather {
  date: string;
  sky: Sky;
  t_max_c: number;
  t_min_c: number;
  temperature_now_c: number;
  sunrise_h: number;
  sunset_h: number;
}

export interface SessionHousehold {
  household_id: string;
  display_name: string;
  start_soc: number;
  guests: number;
  away_from: number | null;
  away_to: number | null;
  work_from_home: boolean;
  panel_derate: number;
  battery_capacity_kwh: number;
}

export interface Session {
  status: SessionStatus;
  sim_date: string;
  start_hour: number;
  horizon_hours: number;
  scenario: Scenario;
  tick_minutes: number;
  hours_delivered: number;
  clock_hours: number;
  retail_tariff: number;
  feed_in_tariff: number;
  peak_surcharge_pct: number;
  power_cut: PowerCut | null;
  weather: Weather;
  households: SessionHousehold[];
}

export interface SlotSummary {
  slot: number;
  day: string;
  hour_of_day: number;
  retail_tariff: number;
  feed_in_tariff: number;
  eb_available: boolean;
  forecast_need_kwh: number;
  forecast_spare_kwh: number;
  p2p_kwh: number;
  p2p_avg_price: number | null;
  eb_bought_kwh: number;
  eb_sold_kwh: number;
  unserved_kwh: number;
  delivered: boolean;
  actual_consumption_kwh: number | null;
  actual_generation_kwh: number | null;
}

export interface AgentMessage {
  household_id: string;
  display_name: string;
  strategy: string;
  side: 'sell' | 'buy' | 'idle';
  firm: boolean;
  quantity_kwh: number;
  limit_price: number | null;
  opening_price: number | null;
  message: string;
  outcome: string;
  reasons: string[];
}

export interface Offer {
  household_id: string;
  side: 'ask' | 'bid';
  price: number;
  kwh: number;
}

export interface SlotTrade {
  buyer_household_id: string;
  seller_household_id: string;
  kwh: number;
  price_per_kwh: number;
  round_index: number;
}

export interface MarketRound {
  round_index: number;
  asks: Offer[];
  bids: Offer[];
  trades: SlotTrade[];
}

export interface EbFlow {
  household_id: string;
  side: 'ask' | 'bid';
  kwh: number;
  price: number;
}

export interface SlotMarket {
  slot: number;
  hour_of_day: number;
  retail_tariff: number;
  feed_in_tariff: number;
  eb_available: boolean;
  rounds: MarketRound[];
  eb_flows: EbFlow[];
  agents: AgentMessage[];
}

export interface HourForecast {
  slot: number;
  day: string;
  hour_of_day: number;
  consumption_p10: number;
  consumption_p50: number;
  consumption_p90: number;
  generation_p10: number;
  generation_p50: number;
  generation_p90: number;
}

export interface OwnSlot {
  slot: number;
  hour_of_day: number;
  forecast: HourForecast;
  p2p_sold_kwh: number;
  p2p_bought_kwh: number;
  eb_bought_kwh: number;
  eb_sold_kwh: number;
  retail_tariff: number;
  feed_in_tariff: number;
  eb_available: boolean;
  decision: AgentMessage | null;
  delivered: boolean;
  actual_consumption_kwh: number | null;
  actual_generation_kwh: number | null;
  actual_eb_import_kwh: number | null;
  actual_eb_export_kwh: number | null;
  actual_unserved_kwh: number | null;
  battery_soc_end: number | null;
}

/** Money is never one signed balance: what was earned and what was paid are
 *  separate, positive figures. */
export interface Statement {
  basis: 'planned' | 'delivered';
  hours: number;
  earned_from_neighbours_inr: number;
  paid_to_neighbours_inr: number;
  paid_to_eb_inr: number;
  earned_from_eb_inr: number;
  eb_only_paid_inr: number;
  eb_only_earned_inr: number;
  saved_vs_eb_only_inr: number;
  units_sold_to_neighbours: number;
  units_bought_from_neighbours: number;
  units_from_eb: number;
  units_to_eb: number;
  units_unserved: number;
}

export interface OwnSession {
  household_id: string;
  model: string;
  slots: OwnSlot[];
  planned: Statement | null;
  delivered: Statement | null;
}

export function fetchSession(accessToken: string, signal?: AbortSignal): Promise<Session> {
  return apiFetch<Session>('/session', accessToken, { signal });
}

export function planSession(accessToken: string, config: SessionConfig): Promise<Session> {
  return apiFetch<Session>('/session/plan', accessToken, { method: 'POST', body: config });
}

export function nextHour(accessToken: string): Promise<Session> {
  return apiFetch<Session>('/session/next-hour', accessToken, { method: 'POST' });
}

export function fetchOverview(accessToken: string, signal?: AbortSignal): Promise<SlotSummary[]> {
  return apiFetch<SlotSummary[]>('/session/overview', accessToken, { signal });
}

export function fetchSlotMarket(
  accessToken: string,
  slot: number,
  signal?: AbortSignal,
): Promise<SlotMarket> {
  return apiFetch<SlotMarket>(`/session/market?slot=${String(slot)}`, accessToken, { signal });
}

export function fetchOwnSession(accessToken: string, signal?: AbortSignal): Promise<OwnSession> {
  return apiFetch<OwnSession>('/households/me/session', accessToken, { signal });
}
