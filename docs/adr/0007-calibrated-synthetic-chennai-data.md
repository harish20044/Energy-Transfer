# 7. Synthetic Chennai data, calibrated to published measurements and checked in CI

- **Status:** Accepted
- **Date:** 2026-10-06

## Context

Every part of the system runs on data: the forecaster trains on it, the agents bid on it, and the demo
plays it out. The microgrid is ten homes with rooftop solar in Chennai, on Tamil Nadu tariffs. No public
dataset gives what that needs: 15-minute rooftop PV output and appliance-level demand for the same Indian
homes, over a full year, with the family behind the load.

Synthetic data is the only practical source. It brings a credibility problem: a simulator can be tuned
to show anything. A panel is right to ask why its numbers should be believed.

## Decision

Generate the data from physical and behavioural models, seeded and deterministic. Then test it against
published Chennai measurements, the way any other code is tested.

**Sun and weather** (`app/simulator/solar.py`, `weather.py`, `climate.py`)

- Solar position from Spencer's declination and the equation of time, at 13.08° N, 80.27° E, IST.
- Clear-sky irradiance from Haurwitz, scaled month by month to NASA POWER's clear-sky climatology.
- Erbs diffuse split, Liu–Jordan transposition to a 13° roof tilt, NOCT cell-temperature derate, and
  14% system losses, to match PVGIS's assumptions.
- Daily rain from a Markov chain fitted to IMD rainy-day normals. Daily clearness is Beta-distributed;
  intra-day cloud follows an AR(1) process.
- Temperature from IMD's monthly mean maximum and minimum, with a Parton–Logan diurnal curve.

**Households** (`app/simulator/family.py`, `household.py`)

- An occupancy-driven appliance model in the style of CREST: each family member is asleep, home or
  away, and appliances follow who is awake and in.
- Families are generated from Indian household patterns: grandparents at home, homemakers, office,
  hybrid and night-shift workers, school and college students, evening tuition, visiting guests.
- Air conditioning, the swing load in Chennai, switches on per bedroom per night through a logistic
  curve on temperature. Inverter ACs draw 0.55–1.45 kW.

**Cross-check** (`app/simulator/validation.py`)

Twenty checks, each pairing one simulated figure with an accepted range from a named source: IMD
1991–2020 normals, NASA POWER, PVGIS 5.3, sunrise-sunset.org, the Prayas eMARC smart-meter study, and
Chennai AC-usage and electricity-bill figures. Each check records its source URL and a note on any
adjustment, for example a Pune benchmark widened for Chennai's heat.

- Weather is judged over 20 synthetic years. Climate normals average decades, and one simulated year is a
  single random draw.
- The suite runs in CI under the `validation` pytest marker. The same code runs as a CLI that prints the
  checks and exports every number behind them as JSON (`--json`).

## Consequences

**Good**

- The data is reproducible from a seed, so a demo, a test and a training run see identical inputs.
- Realism is a test that can fail, not a claim. A calibration change that drifts from Chennai turns CI
  red.
- What-if scenarios (heatwave, monsoon, guests, a family away, no panels) are model inputs rather than
  hand-edited curves, so they stay physically consistent.
- At acceptance, all 20 checks pass. The published cross-check report shows each one with its source.

**Bad / accepted**

- The checks compare averages and patterns. Nothing shows that a simulated day matches any real day in
  any real home.
- Some household benchmarks come from Pune, which is cooler than Chennai. Those ranges were widened by
  judgement, and the note on each check says how. Ranges set by the author could be chosen to pass, so
  every range names its source and states any adjustment.
- The forecaster is trained and scored on this data ([ADR-0010](0010-hourly-forecasts-with-conformal-calibration.md)),
  so its skill reflects how learnable the simulator is. Real meters would be noisier.
