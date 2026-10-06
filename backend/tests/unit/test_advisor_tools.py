"""The advisor's one write tool stays inside the range it declares, whatever
the model sends."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.agents.advisor import ToolContext, build_tools

pytestmark = pytest.mark.unit


class _Db:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _tools() -> tuple[dict[str, Any], SimpleNamespace, _Db]:
    household = SimpleNamespace(id="h1", evening_reserve=0.4)
    db = _Db()
    ctx = ToolContext(
        db=cast(Any, db),
        user=cast(Any, None),
        household=cast(Any, household),
        settings=cast(Any, None),
    )
    return build_tools(ctx), household, db


async def test_the_advisor_sets_a_reserve_the_user_asked_for() -> None:
    tools, household, db = _tools()
    result = await tools["set_reserve"]({"percent": 60})
    assert result["reserve_percent"] == 60
    assert household.evening_reserve == pytest.approx(0.6)
    assert db.commits == 1


@pytest.mark.parametrize(
    "args",
    [{}, {"percent": None}, {"percent": "lots"}, {"percent": 0}, {"percent": 100}, {"percent": 5}],
)
async def test_a_missing_or_out_of_range_reserve_changes_nothing(args: dict[str, Any]) -> None:
    tools, household, db = _tools()
    result = await tools["set_reserve"](args)
    assert "error" in result
    assert household.evening_reserve == pytest.approx(0.4)
    assert db.commits == 0
