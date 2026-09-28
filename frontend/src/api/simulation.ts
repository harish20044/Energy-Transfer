/** Client for the shared simulation clock: state, controls, the negotiation
 *  replay, and market-wide trade/curtailment/topology data. */

import { apiFetch } from '@/api/client';

export type Scenario = 'clear' | 'cloudy' | 'evening_peak' | 'heatwave';

export interface SimulationState {
  tick_index: number;
  running: boolean;
  scenario: Scenario;
  seconds_per_tick: number;
  simulated_day: number;
  simulated_hour: number;
  tick_minutes: number;
  updated_at: string;
}

export interface PlayOptions {
  scenario?: Scenario;
  seconds_per_tick?: number;
}

export interface NegotiationOffer {
  household_id: string;
  side: 'ask' | 'bid';
  price: number;
  kwh: number;
}

export interface MarketTrade {
  tick_index: number;
  round_index: number;
  buyer_household_id: string;
  seller_household_id: string;
  kwh: number;
  price_per_kwh: number;
  created_at: string;
}

export interface NegotiationRound {
  round_index: number;
  asks: NegotiationOffer[];
  bids: NegotiationOffer[];
  trades: MarketTrade[];
}

export interface NegotiationTick {
  tick_index: number;
  rounds: NegotiationRound[];
}

export interface Curtailment {
  tick_index: number;
  buyer_household_id: string;
  seller_household_id: string;
  curtailed_kwh: number;
  reason: string;
  created_at: string;
}

export interface FeederLine {
  id: string;
  from_bus: string;
  to_bus: string;
  thermal_limit_kw: number;
}

export interface Feeder {
  household_ids: string[];
  lines: FeederLine[];
}

export function fetchSimulationState(accessToken: string): Promise<SimulationState> {
  return apiFetch<SimulationState>('/simulation/state', accessToken);
}

export function play(accessToken: string, options: PlayOptions = {}): Promise<SimulationState> {
  return apiFetch<SimulationState>('/simulation/play', accessToken, {
    method: 'POST',
    body: options,
  });
}

export function pause(accessToken: string): Promise<SimulationState> {
  return apiFetch<SimulationState>('/simulation/pause', accessToken, { method: 'POST' });
}

export function step(accessToken: string): Promise<SimulationState> {
  return apiFetch<SimulationState>('/simulation/step', accessToken, { method: 'POST' });
}

export function reset(accessToken: string, options: PlayOptions = {}): Promise<SimulationState> {
  return apiFetch<SimulationState>('/simulation/reset', accessToken, {
    method: 'POST',
    body: options,
  });
}

export function fetchNegotiation(
  accessToken: string,
  tickIndex: number,
  signal?: AbortSignal,
): Promise<NegotiationTick> {
  return apiFetch<NegotiationTick>(`/simulation/negotiation?tick_index=${String(tickIndex)}`, accessToken, {
    signal,
  });
}

export function fetchRecentTrades(
  accessToken: string,
  limit = 50,
  signal?: AbortSignal,
): Promise<MarketTrade[]> {
  return apiFetch<MarketTrade[]>(`/simulation/trades?limit=${String(limit)}`, accessToken, {
    signal,
  });
}

export function fetchRecentCurtailments(
  accessToken: string,
  limit = 50,
  signal?: AbortSignal,
): Promise<Curtailment[]> {
  return apiFetch<Curtailment[]>(`/simulation/curtailments?limit=${String(limit)}`, accessToken, {
    signal,
  });
}

export function fetchNetwork(accessToken: string, signal?: AbortSignal): Promise<Feeder> {
  return apiFetch<Feeder>('/simulation/network', accessToken, { signal });
}
