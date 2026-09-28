"""Train the forecaster and write its artifacts to disk.

    docker exec energy-backend python -m app.forecasting.train

Offline only: builds training data straight from the pure simulator (no
database, no network) and writes six LightGBM model files under
app/forecasting/artifacts/, committed to the repo like any other build
artifact — a fresh checkout can serve real forecasts immediately, without
training on first request.
"""

from __future__ import annotations

import time

import pandas as pd

from app.forecasting.dataset import HouseholdConfig, generate_training_rows
from app.forecasting.model import evaluate, train_models
from app.scripts.seed_households import HOUSEHOLDS

NUM_DAYS = 45
SEED = 42
VALIDATION_FRACTION = 0.15


def main() -> None:
    configs = tuple(
        HouseholdConfig(
            household_id=h.id,
            member_count=h.member_count,
            solar_capacity_kwp=h.solar_capacity_kwp,
        )
        for h in HOUSEHOLDS
    )

    start = time.monotonic()
    rows = generate_training_rows(configs, num_days=NUM_DAYS, seed=SEED)
    df = pd.DataFrame(rows)
    print(f"Generated {len(df)} training rows in {time.monotonic() - start:.1f}s")  # noqa: T201

    shuffled = df.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    split = int(len(shuffled) * (1 - VALIDATION_FRACTION))
    train_df, val_df = shuffled.iloc[:split], shuffled.iloc[split:]

    start = time.monotonic()
    models = train_models(train_df)
    print(f"Trained and saved 6 models in {time.monotonic() - start:.1f}s")  # noqa: T201

    metrics = evaluate(models, val_df)
    print(f"\nHeld-out pinball loss ({len(val_df)} rows):")  # noqa: T201
    for target, quantiles in metrics.items():
        for quantile, loss in quantiles.items():
            print(f"  {target:>15} {quantile}: {loss:.4f}")  # noqa: T201


if __name__ == "__main__":
    main()
