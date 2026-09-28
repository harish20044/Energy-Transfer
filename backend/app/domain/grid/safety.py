"""The grid safety layer: verifies a cleared auction is physically feasible,
and curtails trades until it is. This module holds veto power over the
market — nothing here ever *loosens* a limit to let more trade through.

Curtailing a trade removes that kWh from the shared feeder entirely on both
sides: the seller's export is physically clipped (an ordinary inverter
behaviour, not a fault) and the buyer's matching shortfall reverts to being
met by the retail grid connection instead of a neighbour. That is why
curtailment reduces net injection at *both* parties, not just one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from app.domain.grid import distflow
from app.domain.grid.network import Network
from app.domain.market.auction import Trade

MAX_CURTAILMENT_ROUNDS = 200
_QUANTITY_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class Curtailment:
    buyer_household_id: str
    seller_household_id: str
    curtailed_kwh: float
    reason: str  # e.g. "line substation->h3 thermal limit"


@dataclass(frozen=True, slots=True)
class SafetyResult:
    trades: tuple[Trade, ...]
    curtailments: tuple[Curtailment, ...]
    flow: distflow.FlowResult
    resolved: bool  # False only if MAX_CURTAILMENT_ROUNDS was exhausted


def _net_injection(trades: tuple[Trade, ...]) -> dict[str, float]:
    net: dict[str, float] = {}
    for trade in trades:
        net[trade.seller_household_id] = net.get(trade.seller_household_id, 0.0) + trade.kwh
        net[trade.buyer_household_id] = net.get(trade.buyer_household_id, 0.0) - trade.kwh
    return net


def _worst_thermal_violation(
    network: Network, flow: distflow.FlowResult
) -> tuple[str, float] | None:
    """The line furthest over its thermal limit, as (line_id, excess_kw)."""
    worst: tuple[str, float] | None = None
    for line in network.lines:
        excess_kw = abs(flow.line_flow_kw[line.id]) - line.thermal_limit_kw
        if excess_kw > _QUANTITY_EPSILON and (worst is None or excess_kw > worst[1]):
            worst = (line.id, excess_kw)
    return worst


def _worst_voltage_violation(
    network: Network, flow: distflow.FlowResult
) -> tuple[str, float] | None:
    """The bus furthest outside the statutory voltage band, as
    (bus, excess_pu)."""
    worst: tuple[str, float] | None = None
    for bus, voltage in flow.bus_voltage_pu.items():
        excess_pu = max(0.0, voltage - network.voltage_max_pu, network.voltage_min_pu - voltage)
        if excess_pu > _QUANTITY_EPSILON and (worst is None or excess_pu > worst[1]):
            worst = (bus, excess_pu)
    return worst


def _curtail_largest_trade_in(
    trades: tuple[Trade, ...],
    subtrees: tuple[frozenset[str], ...],
    reduce_by_kwh: float,
    *,
    curtail_side: str,
) -> tuple[tuple[Trade, ...], Curtailment | None]:
    """Reduce the single largest matched trade that actually crosses one of
    `subtrees`' boundaries on its `curtail_side`, by up to `reduce_by_kwh`.

    Which side to curtail depends on which direction of flow is causing the
    violation: exporting too much toward the substation (a reverse-flow
    overload, or a voltage rise above the statutory ceiling) needs
    **sellers** cut back; pulling too much import through a line (an
    ordinary overload, or a voltage sag below the floor) needs **buyers**
    cut back instead — the seller responsible for an import-side violation
    may not even be inside the affected subtree.

    A trade only ever affects a boundary it actually crosses: one where its
    curtailed-side household is inside a subtree and the *other* side is
    outside that same subtree. A trade with both parties on the same side of
    every candidate boundary is internal to all of them — the seller's
    export and the buyer's import cancel exactly, so it contributes nothing
    to any of those boundaries' flow, and curtailing it can never fix a
    violation there. `subtrees` is checked as a union rather than a single
    set for exactly this reason: a voltage violation depends on the
    cumulative drop across *every* segment from the substation down to the
    violated bus, not just the outermost one, so a trade purely internal to
    one lateral can still be the true cause if it crosses one of the
    segments closer to that bus — passing every nested subtree along that
    path, not just the widest one, is what catches it. Whenever a violation
    is genuinely caused by trade flow, a boundary-crossing candidate always
    exists in at least one of them.

    Curtailing the largest offender first (rather than spreading the cut thin
    across many small trades) is deterministic, converges in the fewest
    rounds, and mirrors how a real feeder-management system would act: pull
    back the biggest contributor to an overload first.
    """
    household_of: Callable[[Trade], str] = (
        (lambda trade: trade.seller_household_id)
        if curtail_side == "seller"
        else (lambda trade: trade.buyer_household_id)
    )
    other_household_of: Callable[[Trade], str] = (
        (lambda trade: trade.buyer_household_id)
        if curtail_side == "seller"
        else (lambda trade: trade.seller_household_id)
    )
    candidates = {
        index
        for index, trade in enumerate(trades)
        for subtree in subtrees
        if household_of(trade) in subtree and other_household_of(trade) not in subtree
    }
    if not candidates:
        return trades, None

    # Largest kWh first; ties broken by household id so the outcome is
    # reproducible rather than dependent on dict/list ordering.
    target_index = max(candidates, key=lambda i: (trades[i].kwh, trades[i].seller_household_id))
    target = trades[target_index]

    cut_kwh = min(target.kwh, reduce_by_kwh)
    updated_trades = list(trades)
    remaining_kwh = target.kwh - cut_kwh
    if remaining_kwh > _QUANTITY_EPSILON:
        updated_trades[target_index] = replace(target, kwh=remaining_kwh)
    else:
        del updated_trades[target_index]

    curtailment = Curtailment(
        buyer_household_id=target.buyer_household_id,
        seller_household_id=target.seller_household_id,
        curtailed_kwh=cut_kwh,
        reason="",  # filled in by the caller, which knows which limit this was for
    )
    return tuple(updated_trades), curtailment


def enforce(network: Network, trades: tuple[Trade, ...]) -> SafetyResult:
    """Curtail `trades` until every line and bus is within limits.

    Thermal violations are resolved before voltage violations on each pass —
    an overloaded conductor is an immediate safety issue, a voltage excursion
    a slower-developing one — and the loop always re-checks thermal limits
    first on the next round regardless, so a voltage fix is never allowed to
    reopen a thermal violation.
    """
    current_trades = trades
    curtailments: list[Curtailment] = []

    for _ in range(MAX_CURTAILMENT_ROUNDS):
        flow = distflow.solve(network, _net_injection(current_trades))

        thermal = _worst_thermal_violation(network, flow)
        if thermal is not None:
            line_id, excess_kw = thermal
            line = next(line for line in network.lines if line.id == line_id)
            subtree = network.subtree(line.to_bus)
            # Positive flow = net consumption direction (imports dominate the
            # subtree); negative = reverse flow (exports dominate). See
            # distflow.solve's sign convention.
            side = "buyer" if flow.line_flow_kw[line_id] > 0 else "seller"
            current_trades, cut = _curtail_largest_trade_in(
                current_trades, (subtree,), excess_kw, curtail_side=side
            )
            if cut is None:
                break  # no matching household left in the overloaded subtree
            curtailments.append(replace(cut, reason=f"line {line_id} thermal limit"))
            continue

        voltage = _worst_voltage_violation(network, flow)
        if voltage is not None:
            bus, _excess_pu = voltage
            # The cumulative drop at `bus` is contributed by every segment on
            # the path from the substation down to it, not just the widest
            # one — a household could be the true offender by crossing any
            # single one of those segments, even if it never touches the
            # outermost boundary of the whole lateral. Passing every nested
            # subtree along the path (rather than picking one) is what lets
            # `_curtail_largest_trade_in` find a candidate wherever it
            # actually is, including a trade that's purely internal to this
            # lateral but still crosses an inner segment.
            path = network.path_from_substation(bus)
            subtrees = tuple(network.subtree(line.to_bus) for line in path)
            # A voltage RISE above the ceiling is caused by too much export
            # from within the subtree (reverse flow); a voltage SAG below the
            # floor is caused by too much import INTO the subtree — the
            # seller responsible for that import may be a household on a
            # completely different lateral, so it is the buyers in this
            # subtree that must be curtailed, not the sellers.
            side = "seller" if flow.bus_voltage_pu[bus] > network.voltage_max_pu else "buyer"
            household_of: Callable[[Trade], str] = (
                (lambda t: t.seller_household_id)
                if side == "seller"
                else (lambda t: t.buyer_household_id)
            )
            # Voltage error doesn't convert to kWh directly (it depends on
            # line resistance); curtailing 10% of the whole lateral's current
            # export/import and re-solving converges reliably in a few
            # rounds without needing that conversion.
            lateral_subtree = subtrees[0]
            reduce_by_kwh = 0.1 * sum(
                trade.kwh for trade in current_trades if household_of(trade) in lateral_subtree
            )
            current_trades, cut = _curtail_largest_trade_in(
                current_trades, subtrees, max(reduce_by_kwh, 0.01), curtail_side=side
            )
            if cut is None:
                break
            curtailments.append(replace(cut, reason=f"bus {bus} voltage limit"))
            continue

        return SafetyResult(
            trades=current_trades, curtailments=tuple(curtailments), flow=flow, resolved=True
        )

    final_flow = distflow.solve(network, _net_injection(current_trades))
    return SafetyResult(
        trades=current_trades, curtailments=tuple(curtailments), flow=final_flow, resolved=False
    )
