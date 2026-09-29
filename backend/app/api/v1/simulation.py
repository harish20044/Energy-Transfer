"""Feeder-wide, market-wide data: the network every household trades over,
and the public tape of trades and grid-safety curtailments for the current
session. Driving the session itself lives in `app.api.v1.session`."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.domain.grid.network import default_feeder
from app.engine.session import household_order
from app.models.household import Household
from app.models.simulation import CurtailmentRecord, TradeRecord
from app.schemas.simulation import CurtailmentOut, FeederLineOut, FeederOut, TradeOut

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("/trades", response_model=list[TradeOut])
async def read_recent_trades(
    _current_user: CurrentUserDep,
    db: DbDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[TradeRecord]:
    """Every household's trades this session, in slot order — the same
    transparency a real exchange's public trade tape has. `tick_index` is the
    session slot the trade delivers in."""
    rows = await db.scalars(
        select(TradeRecord).order_by(TradeRecord.tick_index, TradeRecord.id).limit(limit)
    )
    return list(rows)


@router.get("/curtailments", response_model=list[CurtailmentOut])
async def read_recent_curtailments(
    _current_user: CurrentUserDep,
    db: DbDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[CurtailmentRecord]:
    """Every trade the grid safety layer cut back this session — the
    evidence for objective O4."""
    rows = await db.scalars(
        select(CurtailmentRecord).order_by(CurtailmentRecord.tick_index).limit(limit)
    )
    return list(rows)


@router.get("/network", response_model=FeederOut)
async def read_network(_current_user: CurrentUserDep, db: DbDep) -> FeederOut:
    """The feeder topology every household trades over."""
    households = await db.scalars(select(Household).order_by(Household.id))
    household_ids = sorted((h.id for h in households), key=household_order)
    network = default_feeder(household_ids)
    return FeederOut(
        household_ids=household_ids,
        lines=[
            FeederLineOut(
                id=line.id,
                from_bus=line.from_bus,
                to_bus=line.to_bus,
                thermal_limit_kw=line.thermal_limit_kw,
            )
            for line in network.lines
        ],
    )
