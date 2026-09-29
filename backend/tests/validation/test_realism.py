"""The synthetic data, cross-checked against published measurements on every
build: IMD temperature and rainfall normals, NASA POWER irradiance, PVGIS
solar yield, sunrise/sunset times, and Prayas eMARC / Chennai consumption
benchmarks. A failure here means the simulator has drifted from Chennai
reality — the data is deterministic from its seed, so it is never flaky."""

from __future__ import annotations

import pytest

from app.simulator.validation import run_validation

pytestmark = pytest.mark.validation


def test_every_realism_check_passes() -> None:
    report = run_validation()
    failures = [
        f"{c.title}: {c.measured:.2f} {c.unit}, expected {c.low:g}-{c.high:g} ({c.source})"
        for c in report.checks
        if not c.passed
    ]
    assert not failures, "\n".join(failures)
    assert len(report.checks) >= 20
