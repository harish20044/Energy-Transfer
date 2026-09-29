/** Turns a settled neighbour trade into the shape the trade list and
 *  decision-record UI read — the one place that decides how a trade reads
 *  from this household's side (buyer or seller). Its rationale is the
 *  household agent's own recorded message for that hour, not a new guess. */

import type { MarketTrade } from '@/api/simulation';
import { hourLabel } from '@/lib/format';
import { householdLabel } from '@/lib/household';
import type { Trade } from '@/types/energy';

export function toUiTrade(
  trade: MarketTrade,
  ownHouseholdId: string,
  startHour: number,
  agentRationale: string | null = null,
  curtailedReason: string | null = null,
): Trade {
  const isSell = trade.seller_household_id === ownHouseholdId;
  const counterpartyId = isSell ? trade.buyer_household_id : trade.seller_household_id;
  const roundLabel = `in round ${String(trade.round_index + 1)} of the negotiation`;
  const fallback = isSell
    ? `Sold ${trade.kwh.toFixed(2)} units to ${householdLabel(counterpartyId)} at ₹${trade.price_per_kwh.toFixed(2)}/unit, matching ${roundLabel}.`
    : `Bought ${trade.kwh.toFixed(2)} units from ${householdLabel(counterpartyId)} at ₹${trade.price_per_kwh.toFixed(2)}/unit, matching ${roundLabel}.`;

  return {
    id: `${String(trade.tick_index)}-${trade.seller_household_id}-${trade.buyer_household_id}-${String(trade.round_index)}`,
    slot: trade.tick_index,
    at: hourLabel(startHour + trade.tick_index),
    counterparty: householdLabel(counterpartyId),
    side: isSell ? 'sell' : 'buy',
    kwh: trade.kwh,
    pricePerKwh: trade.price_per_kwh,
    totalInr: trade.kwh * trade.price_per_kwh,
    rationale: agentRationale ?? fallback,
    bindingConstraint: curtailedReason,
  };
}
