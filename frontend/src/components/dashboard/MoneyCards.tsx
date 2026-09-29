import { ArrowDownToLine, ArrowUpFromLine, Landmark, PiggyBank, Zap } from 'lucide-react';

import type { Statement } from '@/api/session';
import { StatTile } from '@/components/ui/StatTile';
import { inr, kwh } from '@/lib/format';

/** Money the way an EB bill shows it: what was paid and what was earned as
 *  separate amounts, never one signed "balance". */
export function MoneyCards({ statement }: { statement: Statement }) {
  const saved = statement.saved_vs_eb_only_inr;
  const basis =
    statement.basis === 'delivered'
      ? `${String(statement.hours)} hour${statement.hours === 1 ? '' : 's'} delivered`
      : `planned, ${String(statement.hours)} hours`;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
      <StatTile
        label="Earned from neighbours"
        value={inr(statement.earned_from_neighbours_inr)}
        caption={`${kwh(statement.units_sold_to_neighbours)} sold · ${basis}`}
        icon={ArrowUpFromLine}
        tone="solar"
      />
      <StatTile
        label="Paid to neighbours"
        value={inr(statement.paid_to_neighbours_inr)}
        caption={`${kwh(statement.units_bought_from_neighbours)} bought`}
        icon={ArrowDownToLine}
        tone="peer"
      />
      <StatTile
        label="Paid to the EB"
        value={inr(statement.paid_to_eb_inr)}
        caption={`${kwh(statement.units_from_eb)} imported`}
        icon={Zap}
        tone="grid"
      />
      <StatTile
        label="Earned from the EB"
        value={inr(statement.earned_from_eb_inr)}
        caption={`${kwh(statement.units_to_eb)} exported`}
        icon={Landmark}
        tone="neutral"
      />
      <StatTile
        label={saved >= 0 ? 'Saved vs EB alone' : 'Cost vs EB alone'}
        value={inr(Math.abs(saved))}
        caption={
          saved >= 0
            ? `EB alone: paid ${inr(statement.eb_only_paid_inr)}, earned ${inr(statement.eb_only_earned_inr)}`
            : 'forecast errors cost more than trading saved'
        }
        icon={PiggyBank}
        tone="battery"
      />
    </div>
  );
}
