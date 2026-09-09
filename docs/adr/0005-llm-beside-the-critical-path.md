# 5. The LLM sits beside the trading path, never inside it

- **Status:** Accepted
- **Date:** 2026-09-09
- **Refines:** the "Decision LLM: Llama 3.1 8B via Ollama" row of the Zeroth Review stack

## Context

The reviewed stack placed Llama 3.1 8B in the decision path — the LLM would decide trades. Three
independent objections:

1. **Determinism.** Money moves and grid safety is at stake. A trade must be reproducible and auditable:
   given identical inputs, an identical allocation, explainable to a regulator or a homeowner disputing a
   bill. Sampling from a language model is neither reproducible nor auditable.
2. **Latency and throughput.** Objective **O3** targets p95 below 200 ms for 100 agents. The development
   machine has no discrete GPU (Intel UHD only), where an 8B model runs at roughly 3–8 tok/s. Fifty
   agents × 96 ticks/day × one call each is physically impossible on this hardware, and unjustifiably
   expensive on any other.
3. **Failure blast radius.** If the market cannot clear when the model is rate-limited, slow or down,
   then an LLM outage becomes an energy-trading outage.

But discarding the LLM entirely would forfeit real value: explanation, natural-language preferences and
anomaly triage are genuinely language problems.

## Decision

Split the responsibilities.

**Critical path — deterministic, no LLM:** forecasting, bid/ask derivation, auction clearing, grid safety
checking, settlement. Pure functions in `app/domain/`, property-tested, reproducible from a seed.

**Beside the path — LLM:**
- **Explanation.** Natural-language rationale for each household's outcome (objective **O7**), generated
  after settlement, cached, never blocking.
- **Preference interpretation.** Turning "keep 40% charge for the evening" into typed constraints, which
  are validated by Pydantic before they can influence anything.
- **Anomaly triage.** Summarising unusual tick outcomes for the operator.

An LLM failure degrades explanations to a deterministic template. Trading and settlement are untouched.

The LLM is reached through a **provider interface** (`app/agents/llm.py`) with three implementations
selected by the `LLM_PROVIDER` environment variable:

| Provider | Role | Notes |
|---|---|---|
| `groq` | **default** | Free tier, Llama 3.3 70B at ~275 tok/s. No GPU required, and a far stronger model than an 8B local one. |
| `ollama` | offline / privacy | Runs on the host, not in Compose. Reached at `host.docker.internal:11434`. |
| `stub` | CI and tests | Deterministic canned responses — CI needs no key, no model and no network. |

All three return the same Pydantic-validated structured output, so no caller can tell them apart.

## Consequences

**Good**

- Trading is reproducible, auditable and fast; O3 is achievable on ordinary hardware.
- An LLM outage or rate limit cannot stop the market.
- CI is hermetic and free — no API key ever enters a workflow.
- A local-vs-cloud comparison of explanation quality and latency falls out of the design at no extra cost,
  which is a thesis asset.

**Bad / accepted**

- This is a weaker claim than "an LLM trades autonomously". It is also the defensible one, and the
  agents remain genuinely autonomous — LangGraph state machines owning strategy, battery policy and risk
  posture.
- Three provider implementations to maintain. Contained by a narrow interface and one shared contract test
  applied to all three.
