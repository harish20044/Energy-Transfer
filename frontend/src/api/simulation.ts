/** Feeder-wide data: the network every household trades over, and the
 *  session's public tape of grid-safety curtailments. Driving
 *  the session itself lives in `@/api/session`. */

import { apiFetch } from '@/api/client';

/** A settled neighbour trade. `tick_index` is the session slot (hour) it
 *  delivers in. */
export interface MarketTrade {
  tick_index: number;
  round_index: number;
  buyer_household_id: string;
  seller_household_id: string;
  kwh: number;
  price_per_kwh: number;
  created_at: string;
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

export function fetchRecentCurtailments(
  accessToken: string,
  limit = 200,
  signal?: AbortSignal,
): Promise<Curtailment[]> {
  return apiFetch<Curtailment[]>(`/simulation/curtailments?limit=${String(limit)}`, accessToken, {
    signal,
  });
}

export function fetchNetwork(accessToken: string, signal?: AbortSignal): Promise<Feeder> {
  return apiFetch<Feeder>('/simulation/network', accessToken, { signal });
}
