"""Run the full evaluation and write the report.

docker exec energy-backend python -m app.evaluation              # everything
docker exec energy-backend python -m app.evaluation --sessions 2 --no-scale   # quick look
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.memory import AgentMemory
from app.core.config import get_settings
from app.evaluation.forecast import evaluate_forecaster
from app.evaluation.metrics import session_metrics, summarise
from app.evaluation.report import render_markdown
from app.evaluation.runner import run_session, scaled_households, seed_households
from app.evaluation.suite import SCALE_HOUSEHOLDS, SCALE_SESSION, SUITE


def _log(message: str) -> None:
    print(message, flush=True)  # noqa: T201


def run(*, sessions: int, scale: bool, ac: bool) -> dict[str, Any]:
    settings = get_settings()
    started = time.monotonic()
    _log("O1 · scoring the forecaster on held-out test days…")
    forecast = evaluate_forecaster()

    memories: dict[str, AgentMemory] = {}
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for spec in SUITE[:sessions]:
        _log(f"Session · {spec.name}")
        try:
            outcome = run_session(
                spec,
                seed_households(),
                memories=memories,
                seed=settings.sim_seed,
                tick_minutes=settings.market_tick_minutes,
            )
        # A session that fails is itself a result (O3 autonomy), not a crash.
        except Exception as exc:
            failures.append({"session": spec.name, "error": repr(exc)})
            continue
        memories = outcome.memories
        results.append(session_metrics(outcome, with_ac=ac))

    scale_metrics: dict[str, Any]
    if scale:
        _log(f"Scale · {SCALE_SESSION.name}")
        scale_run = run_session(
            SCALE_SESSION,
            scaled_households(SCALE_HOUSEHOLDS),
            memories={},
            seed=settings.sim_seed,
            tick_minutes=settings.market_tick_minutes,
        )
        scale_metrics = session_metrics(scale_run, with_ac=ac)
    else:
        scale_metrics = results[-1]

    summary = summarise(results, scale_metrics, failed_sessions=len(failures))
    summary["O1"] = {"met": forecast["met"], **forecast["targets"]}
    return {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "runtime_seconds": time.monotonic() - started,
        "seed": settings.sim_seed,
        "forecast": forecast,
        "sessions": results,
        "scale": scale_metrics,
        "scale_run": scale,
        "failures": failures,
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Measure objectives O1-O7.")
    parser.add_argument("--out", default="docs", help="directory for evaluation.md/.json")
    parser.add_argument("--sessions", type=int, default=len(SUITE), help="first N suite sessions")
    parser.add_argument("--no-scale", action="store_true", help="skip the 100-home session")
    parser.add_argument("--no-ac", action="store_true", help="skip the AC power-flow check")
    args = parser.parse_args(argv)

    results = run(sessions=args.sessions, scale=not args.no_scale, ac=not args.no_ac)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "evaluation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (out / "evaluation.md").write_text(render_markdown(results), encoding="utf-8")
    _log(f"Wrote {out / 'evaluation.md'} in {results['runtime_seconds']:.0f}s")
    for key, value in sorted(results["summary"].items()):
        _log(f"  {key}: {'met' if value['met'] else 'NOT met'}")


if __name__ == "__main__":
    main()
