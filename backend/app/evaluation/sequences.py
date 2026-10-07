"""Inputs for the LSTM benchmark (`app.evaluation.lstm`), built from the very
rows LightGBM trains and is tested on: the household's last
`HISTORY_HOURS` of metered load and solar as a sequence, plus the same
calendar, family, weather and astronomy features LightGBM sees for the
target hour. Pure numpy, so it is tested without PyTorch installed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from app.forecasting.features import FEATURE_COLUMNS, TARGET_CONSUMPTION, TARGET_GENERATION

HISTORY_HOURS = 24
Array = npt.NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class Scaler:
    """Standardisation fitted on training rows only."""

    sequence_mean: Array  # per channel (load, solar)
    sequence_std: Array
    static_mean: Array  # per feature
    static_std: Array


@dataclass(frozen=True, slots=True)
class SequenceInputs:
    sequence: Array  # rows x HISTORY_HOURS x 2, oldest hour first
    static: Array  # rows x len(FEATURE_COLUMNS)
    target: Array  # rows x 2: (load, solar) kW


def history_columns(channel: str, hours: int = HISTORY_HOURS) -> list[str]:
    """Oldest first: the sequence reads forward in time."""
    return [f"hist_{channel}_{back}" for back in range(hours, 0, -1)]


def raw_inputs(df: pd.DataFrame, hours: int = HISTORY_HOURS) -> SequenceInputs:
    sequence = np.stack(
        [
            df[history_columns("consumption", hours)].to_numpy(dtype=np.float32),
            df[history_columns("generation", hours)].to_numpy(dtype=np.float32),
        ],
        axis=-1,
    )
    return SequenceInputs(
        sequence=sequence,
        static=df[list(FEATURE_COLUMNS)].to_numpy(dtype=np.float32),
        target=df[[TARGET_CONSUMPTION, TARGET_GENERATION]].to_numpy(dtype=np.float32),
    )


def fit_scaler(inputs: SequenceInputs) -> Scaler:
    def safe_std(values: Array) -> Array:
        std: Array = values.std(axis=0)
        return np.where(std > 1e-6, std, 1.0).astype(np.float32)

    flat = inputs.sequence.reshape(-1, inputs.sequence.shape[-1])
    return Scaler(
        sequence_mean=flat.mean(axis=0).astype(np.float32),
        sequence_std=safe_std(flat),
        static_mean=inputs.static.mean(axis=0).astype(np.float32),
        static_std=safe_std(inputs.static),
    )


def scale(inputs: SequenceInputs, scaler: Scaler) -> SequenceInputs:
    return SequenceInputs(
        sequence=((inputs.sequence - scaler.sequence_mean) / scaler.sequence_std).astype(
            np.float32
        ),
        static=((inputs.static - scaler.static_mean) / scaler.static_std).astype(np.float32),
        target=inputs.target,
    )
