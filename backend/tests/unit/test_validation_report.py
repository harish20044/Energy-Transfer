"""The cross-check report exports cleanly, whatever numeric types the
simulator hands it."""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.simulator.validation import Check, ValidationReport

pytestmark = pytest.mark.unit


def test_the_report_exports_numpy_measurements_as_plain_json() -> None:
    report = ValidationReport(
        checks=[
            Check("pv", "Solar", "Annual yield", np.float32(1494.0), 1400, 1600, "kWh", "s", "u"),
            Check("ac", "Load", "AC hours", np.float64(12.0), 6, 10, "h", "s", "u"),
        ],
        series={"pv": list(np.array([1.0, 2.0], dtype=np.float32))},
    )
    exported = json.loads(json.dumps(report.to_json()))
    assert [c["passed"] for c in exported["checks"]] == [True, False]
    assert exported["passed"] is False
    assert exported["series"]["pv"] == [1.0, 2.0]
