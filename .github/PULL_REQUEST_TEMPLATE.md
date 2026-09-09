## What and why

<!-- What changes, and what problem it solves. Link the phase or objective it advances. -->

## Objectives touched

<!-- Delete any that do not apply. -->

- [ ] O1 forecasting accuracy
- [ ] O2 matching efficiency
- [ ] O3 autonomy / latency
- [ ] O4 grid safety (zero violations)
- [ ] O5 renewable utilisation
- [ ] O6 economic benefit / individual rationality
- [ ] O7 explainability
- [ ] None — infrastructure, docs or tooling

## Checklist

- [ ] `ruff check`, `ruff format --check`, `mypy app` and `pytest` pass
- [ ] Frontend `lint`, `format:check`, `typecheck`, `test:run` and `build` pass
- [ ] New behaviour is covered by tests; invariants are covered by **property** tests
- [ ] Nothing under `app/domain/` performs I/O ([ADR-0006](../docs/adr/0006-pure-domain-layer.md))
- [ ] Architecturally significant decisions are recorded as an ADR
- [ ] No secrets, keys or real personal data added

## Verification

<!-- How a reviewer can confirm this works. Commands, endpoints, screenshots. -->
