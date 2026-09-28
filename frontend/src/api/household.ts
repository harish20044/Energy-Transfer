/** Client for a household's own view of itself — every call here resolves
 *  to "my household" purely from the bearer token; none of them accept a
 *  household id, mirroring the backend's isolation guarantee. */

import { apiFetch } from '@/api/client';
import type { MarketTrade } from '@/api/simulation';

export interface HouseholdProfile {
  id: string;
  display_name: string;
  member_count: number;
  solar_capacity_kwp: number;
  battery_capacity_kwh: number;
  battery_max_charge_kw: number;
  battery_max_discharge_kw: number;
  evening_reserve: number;
}

export interface MeterReading {
  tick_index: number;
  consumption_kw: number;
  generation_kw: number;
  battery_soc: number;
  battery_action: 'charging' | 'discharging' | 'idle';
  grid_kwh: number;
  created_at: string;
}

export interface HouseholdBalance {
  household_id: string;
  net_balance: number;
  total_sold_kwh: number;
  total_bought_kwh: number;
}

export function fetchOwnHousehold(
  accessToken: string,
  signal?: AbortSignal,
): Promise<HouseholdProfile> {
  return apiFetch<HouseholdProfile>('/households/me', accessToken, { signal });
}

export function updateEveningReserve(
  accessToken: string,
  eveningReserve: number,
): Promise<HouseholdProfile> {
  return apiFetch<HouseholdProfile>('/households/me/evening-reserve', accessToken, {
    method: 'PATCH',
    body: { evening_reserve: eveningReserve },
  });
}

export function fetchOwnReadings(
  accessToken: string,
  limit = 96,
  signal?: AbortSignal,
): Promise<MeterReading[]> {
  return apiFetch<MeterReading[]>(`/households/me/readings?limit=${String(limit)}`, accessToken, {
    signal,
  });
}

export function fetchOwnTrades(
  accessToken: string,
  limit = 50,
  signal?: AbortSignal,
): Promise<MarketTrade[]> {
  return apiFetch<MarketTrade[]>(`/households/me/trades?limit=${String(limit)}`, accessToken, {
    signal,
  });
}

export function fetchOwnBalance(
  accessToken: string,
  signal?: AbortSignal,
): Promise<HouseholdBalance> {
  return apiFetch<HouseholdBalance>('/households/me/balance', accessToken, { signal });
}
