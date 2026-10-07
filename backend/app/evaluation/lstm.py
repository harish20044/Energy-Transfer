"""The LSTM benchmark for objective O1 (ADR-0004): a PyTorch sequence model,
trained and calibrated exactly as the served LightGBM forecaster is, then
scored on the same held-out test days by the same scorer. Offline only — it
is never served — and it needs the optional `bench` extra (PyTorch), so it
runs in its own image:

    docker compose --profile bench run --rm bench python -m app.evaluation.lstm

Model: an LSTM over the household's last 24 hours of load and solar; its
final state, joined with the LightGBM features for the target hour, feeds a
small network with six outputs — P10/P50/P90 for load and for solar —
trained on pinball loss. Calibrated with the same asymmetric conformal step
(`app.forecasting.model.conformal_offsets`) on the same calibration days.
The result lands in `app/forecasting/artifacts/lstm_benchmark.json`, which
`app.evaluation.forecast` folds into the O1 comparison.
"""

from __future__ import annotations

import json
import time
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch import nn

from app.evaluation.forecast import LSTM_RESULT_FILE
from app.evaluation.sequences import (
    HISTORY_HOURS,
    SequenceInputs,
    fit_scaler,
    raw_inputs,
    scale,
)
from app.forecasting.dataset import HouseholdConfig, generate_training_rows
from app.forecasting.model import (
    QUANTILES,
    TARGETS,
    conformal_offsets,
    finish_quantiles,
    load_conformal,
    load_models,
    predict_batch,
    score_quantiles,
    seasonal_naive_predictions,
)
from app.forecasting.train import NUM_DAYS, SEED, SPLIT_MODULUS, TRAINING_YEAR_START
from app.scripts.seed_households import HOUSEHOLDS

HIDDEN = 64
EPOCHS = 12
BATCH = 512
LEARNING_RATE = 1e-3
_QUANTILE_LEVELS = torch.tensor(list(QUANTILES.values()))


class QuantileLSTM(nn.Module):
    def __init__(self, static_features: int) -> None:
        super().__init__()
        self.lstm = nn.LSTM(input_size=2, hidden_size=HIDDEN, batch_first=True)
        self.head = nn.Sequential(
            nn.Linear(HIDDEN + static_features, 64),
            nn.ReLU(),
            nn.Linear(64, len(TARGETS) * len(QUANTILES)),
        )

    def forward(self, sequence: torch.Tensor, static: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.lstm(sequence)
        joined = torch.cat([hidden[-1], static], dim=1)
        out: torch.Tensor = self.head(joined).view(-1, len(TARGETS), len(QUANTILES))
        return out


def pinball(prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    diff = target.unsqueeze(-1) - prediction
    levels = _QUANTILE_LEVELS.to(prediction.dtype)
    return torch.maximum(levels * diff, (levels - 1) * diff).mean()


def _tensors(inputs: SequenceInputs) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    return (
        torch.from_numpy(inputs.sequence),
        torch.from_numpy(inputs.static),
        torch.from_numpy(inputs.target),
    )


def train(inputs: SequenceInputs) -> tuple[QuantileLSTM, list[float]]:
    torch.manual_seed(SEED)
    model = QuantileLSTM(inputs.static.shape[1])
    optimiser = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    sequence, static, target = _tensors(inputs)
    generator = torch.Generator().manual_seed(SEED)
    losses: list[float] = []
    for epoch in range(EPOCHS):
        model.train()
        order = torch.randperm(len(target), generator=generator)
        total = 0.0
        for start in range(0, len(order), BATCH):
            batch = order[start : start + BATCH]
            optimiser.zero_grad()
            loss = pinball(model(sequence[batch], static[batch]), target[batch])
            loss.backward()  # type: ignore[no-untyped-call]
            optimiser.step()
            total += loss.item() * len(batch)
        losses.append(total / len(order))
        print(f"  epoch {epoch + 1}/{EPOCHS}: pinball {losses[-1]:.4f}", flush=True)  # noqa: T201
    return model, losses


def predict_raw(model: QuantileLSTM, inputs: SequenceInputs) -> dict[str, np.ndarray]:
    model.eval()
    sequence, static, _ = _tensors(inputs)
    chunks = []
    with torch.no_grad():
        for start in range(0, len(static), 8192):
            chunks.append(model(sequence[start : start + 8192], static[start : start + 8192]))
    out = torch.cat(chunks).numpy().astype(np.float64)
    return {target: out[:, i, :] for i, target in enumerate(TARGETS)}


def main() -> None:
    configs = tuple(HouseholdConfig(h.id, h.member_count, h.solar_capacity_kwp) for h in HOUSEHOLDS)
    started = time.monotonic()
    df = pd.DataFrame(
        generate_training_rows(
            configs,
            start=TRAINING_YEAR_START,
            num_days=NUM_DAYS,
            seed=SEED,
            history_hours=HISTORY_HOURS,
        )
    )
    print(f"Generated {len(df):,} rows in {time.monotonic() - started:.0f}s", flush=True)  # noqa: T201
    split = df["day_of_year"].astype(int) % SPLIT_MODULUS
    fit_df, calibration_df, test_df = df[split >= 2], df[split == 1], df[split == 0]

    raw_fit = raw_inputs(fit_df)
    scaler = fit_scaler(raw_fit)
    started = time.monotonic()
    model, losses = train(scale(raw_fit, scaler))
    train_seconds = time.monotonic() - started

    calibration_raw = finish_quantiles(
        predict_raw(model, scale(raw_inputs(calibration_df), scaler)), calibration_df
    )
    offsets = conformal_offsets(calibration_raw, calibration_df)
    test_out = predict_raw(model, scale(raw_inputs(test_df), scaler))
    scores: dict[str, Any] = {
        "lstm_raw": score_quantiles(test_df, finish_quantiles(test_out, test_df)),
        "lstm_calibrated": score_quantiles(test_df, finish_quantiles(test_out, test_df, offsets)),
        "seasonal_naive": score_quantiles(test_df, seasonal_naive_predictions(test_df)),
    }
    models = load_models()
    if models:
        scores["lightgbm_calibrated"] = score_quantiles(
            test_df, predict_batch(models, test_df, load_conformal())
        )

    LSTM_RESULT_FILE.write_text(
        json.dumps(
            {
                "model": (
                    f"LSTM({HISTORY_HOURS} h of load and solar, hidden {HIDDEN}) "
                    "+ target-hour features -> P10/P50/P90 x 2"
                ),
                "parameters": sum(p.numel() for p in model.parameters()),
                "epochs": EPOCHS,
                "batch": BATCH,
                "learning_rate": LEARNING_RATE,
                "train_rows": len(fit_df),
                "test_rows": len(test_df),
                "train_seconds": train_seconds,
                "epoch_losses": losses,
                "torch": torch.__version__,
                "scores": scores,
            },
            indent=2,
        )
    )
    for name, by_target in scores.items():
        for target, m in by_target.items():
            print(  # noqa: T201
                f"{name:20} {target:15} pinball {m['pinball']:.4f}  nMAE {m['nmae_p50']:.3f}  "
                f"coverage {m['p10_p90_coverage']:.1%}"
            )


if __name__ == "__main__":
    main()
