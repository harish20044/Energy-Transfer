/** Small derivations shared across the household views — turning the raw
 *  per-tick rows the API returns into the instantaneous kW figures the UI
 *  actually displays. */

import type { MarketTrade } from '@/api/simulation';

/** This household's net position with its neighbours for one tick, in kW.
 *  Positive means it sold more than it bought that tick. */
export function ownMarketKw(
  trades: MarketTrade[],
  householdId: string,
  tickIndex: number,
  tickMinutes: number,
): number {
  const durationH = tickMinutes / 60;
  const thisTick = trades.filter((trade) => trade.tick_index === tickIndex);
  const soldKwh = thisTick
    .filter((trade) => trade.seller_household_id === householdId)
    .reduce((total, trade) => total + trade.kwh, 0);
  const boughtKwh = thisTick
    .filter((trade) => trade.buyer_household_id === householdId)
    .reduce((total, trade) => total + trade.kwh, 0);
  return (soldKwh - boughtKwh) / durationH;
}

/** How many distinct neighbours this household traded with this tick. */
export function tradingPartnerCount(
  trades: MarketTrade[],
  householdId: string,
  tickIndex: number,
): number {
  const partners = new Set<string>();
  for (const trade of trades) {
    if (trade.tick_index !== tickIndex) continue;
    if (trade.seller_household_id === householdId) partners.add(trade.buyer_household_id);
    if (trade.buyer_household_id === householdId) partners.add(trade.seller_household_id);
  }
  return partners.size;
}
