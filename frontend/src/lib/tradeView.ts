/** Turns a raw settled trade from the API into the shape the trade-list and
 *  decision-record UI components read — the one place that decides how a
 *  trade reads from this household's point of view (buyer or seller) and
 *  generates its plain-language explanation.
 *
 *  The "rationale" is a deterministic template over the trade's own fields,
 *  not an LLM call — narration stays off the trading critical path (see
 *  docs/adr/0005), so this is always present, instant, and reproducible.
 */

import type { MarketTrade } from '@/api/simulation';
import { householdLabel } from '@/lib/household';
import { simClock } from '@/lib/format';
import type { Trade } from '@/types/energy';

export function toUiTrade(
  trade: MarketTrade,
  ownHouseholdId: string,
  tickMinutes: number,
  curtailedReason: string | null = null,
): Trade {
  const isSell = trade.seller_household_id === ownHouseholdId;
  const counterpartyId = isSell ? trade.buyer_household_id : trade.seller_household_id;
  const totalInr = trade.kwh * trade.price_per_kwh;
  const roundLabel =
    trade.round_index === 0 ? 'immediately' : `after ${String(trade.round_index)} rounds of negotiation`;

  const rationale = isSell
    ? `Sold ${trade.kwh.toFixed(2)} units to ${householdLabel(counterpartyId)} at ₹${trade.price_per_kwh.toFixed(2)}/unit, matching ${roundLabel}.`
    : `Bought ${trade.kwh.toFixed(2)} units from ${householdLabel(counterpartyId)} at ₹${trade.price_per_kwh.toFixed(2)}/unit, matching ${roundLabel}.`;

  return {
    id: `${String(trade.tick_index)}-${trade.seller_household_id}-${trade.buyer_household_id}-${String(trade.round_index)}`,
    at: simClock((trade.tick_index * tickMinutes) / 60),
    counterparty: householdLabel(counterpartyId),
    side: isSell ? 'sell' : 'buy',
    kwh: trade.kwh,
    pricePerKwh: trade.price_per_kwh,
    totalInr,
    rationale,
    bindingConstraint: curtailedReason,
  };
}
