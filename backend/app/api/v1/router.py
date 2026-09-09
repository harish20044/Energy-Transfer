"""Aggregates every v1 route onto a single router.

Later phases attach their routers here: households, market, forecast, ledger,
auth and the WebSocket stream.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
