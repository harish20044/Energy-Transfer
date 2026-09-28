/** Client for a household's next 1-4 hour buy/sell forecast. */

import { apiFetch } from '@/api/client';

export type RecommendedAction = 'buy' | 'sell' | 'hold';

export interface HourForecast {
  horizon_hours: number;
  hour_of_day: number;
  consumption_p10: number;
  consumption_p50: number;
  consumption_p90: number;
  generation_p10: number;
  generation_p50: number;
  generation_p90: number;
  net_p50_kw: number;
  recommended_action: RecommendedAction;
  projected_net_for_market_kw: number;
}

export interface Forecast {
  household_id: string;
  model: 'lightgbm-quantile' | 'seasonal-naive';
  hours: HourForecast[];
}

export function fetchOwnForecast(accessToken: string, signal?: AbortSignal): Promise<Forecast> {
  return apiFetch<Forecast>('/households/me/forecast', accessToken, { signal });
}
