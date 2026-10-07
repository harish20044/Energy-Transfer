"""Objective O2 as `docs/objectives.md` defines it: the auction's allocative
efficiency (Smith, 1962; Gode & Sunder, 1993).

Each slot's welfare is the gain from trade the households themselves stated
in their orders — for every matched kWh, the buyer's limit price (what it
was worth to them) less the seller's limit price (what it cost them):

    W = sum over trades of (buyer's limit - seller's limit) x kWh

The benchmark is the offline optimum over the same orders: a linear program
that sees every order of the slot at once and matches them to maximise W,
subject to the same grid constraints the safety layer enforces (line
thermal limits, the operating voltage band). Efficiency is the realised W
over the optimal W, pooled over slots.

A uniform-price market lets any buyer match any seller, and line flows
depend only on each household's net position, so the optimum needs only
each household's volume bought and sold, not who traded with whom.

This is distinct from the perfect-foresight comparison in
`app.evaluation.optimum`, which also knows every home's actual load and
solar in advance and so measures the price of forecasting, not the auction.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from app.domain.grid.network import Network
from app.domain.market.orderbook import Side
from app.engine.market_run import ClearedSlot


@dataclass(frozen=True, slots=True)
class SlotWelfare:
    realised_inr: float
    optimal_inr: float


def slot_welfare(cleared: ClearedSlot, network: Network) -> SlotWelfare:
    fit, retail = cleared.clearing.feed_in_tariff, cleared.clearing.retail_tariff

    def clamp(price: float) -> float:
        # The market clamps every limit into the tariff band; so does this.
        return min(retail, max(fit, price))

    bids: dict[str, tuple[float, float]] = {}  # household -> (kWh, limit)
    asks: dict[str, tuple[float, float]] = {}
    for hid, part in cleared.households.items():
        for order in part.decision.orders:
            book = bids if order.side is Side.BID else asks
            book[hid] = (order.kwh, clamp(order.limit_price))

    realised = sum(
        trade.kwh * (bids[trade.buyer_household_id][1] - asks[trade.seller_household_id][1])
        for trade in cleared.clearing.safety.trades
    )
    return SlotWelfare(realised_inr=realised, optimal_inr=_optimal(bids, asks, network))


def _optimal(
    bids: dict[str, tuple[float, float]],
    asks: dict[str, tuple[float, float]],
    network: Network,
) -> float:
    if not bids or not asks or max(b[1] for b in bids.values()) < min(a[1] for a in asks.values()):
        return 0.0
    buyers, sellers = list(bids), list(asks)
    n_buy = len(buyers)
    size = n_buy + len(sellers)
    # Variables: kWh bought by each bidder, then kWh sold by each asker.
    cost = np.array([-bids[h][1] for h in buyers] + [asks[h][1] for h in sellers])
    bounds = [(0.0, bids[h][0]) for h in buyers] + [(0.0, asks[h][0]) for h in sellers]
    a_eq = np.array([[1.0] * n_buy + [-1.0] * len(sellers)])

    # Net injection per household: + sold - bought.
    injection: dict[str, dict[int, float]] = {}
    for i, h in enumerate(buyers):
        injection.setdefault(h, {})[i] = -1.0
    for j, h in enumerate(sellers):
        injection.setdefault(h, {})[n_buy + j] = 1.0

    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    rhs: list[float] = []

    def le(terms: dict[int, float], bound: float) -> None:
        row = len(rhs)
        for col, val in terms.items():
            rows.append(row)
            cols.append(col)
            vals.append(val)
        rhs.append(bound)

    flows: dict[str, dict[int, float]] = {}
    for line in network.lines:
        flow: dict[int, float] = {}
        for bus in network.subtree(line.to_bus):
            for col, sign in injection.get(bus, {}).items():
                flow[col] = flow.get(col, 0.0) - sign  # flow = -(net export downstream)
        flows[line.id] = flow
        if flow:
            le(flow, line.thermal_limit_kw)
            le({k: -v for k, v in flow.items()}, line.thermal_limit_kw)
    for bus in network.household_buses():
        drop: dict[int, float] = {}
        for line in network.path_from_substation(bus):
            for col, coeff in flows[line.id].items():
                drop[col] = drop.get(col, 0.0) + line.resistance_pu * coeff
        if drop:
            le({k: -v for k, v in drop.items()}, network.operating_max_pu - 1.0)
            le(drop, 1.0 - network.operating_min_pu)

    a_ub = coo_matrix((vals, (rows, cols)), shape=(len(rhs), size)).tocsr() if rhs else None
    result = linprog(
        cost,
        A_ub=a_ub,
        b_ub=np.array(rhs) if rhs else None,
        A_eq=a_eq,
        b_eq=np.array([0.0]),
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        msg = f"allocative optimum failed: {result.message}"
        raise RuntimeError(msg)
    return max(0.0, -float(result.fun))
