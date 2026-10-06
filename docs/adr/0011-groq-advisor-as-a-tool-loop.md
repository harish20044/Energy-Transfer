# 11. The household advisor: a tool-using LLM on Groq, beside the trading path

- **Status:** Accepted
- **Date:** 2026-10-06
- **Refines:** [ADR-0005](0005-llm-beside-the-critical-path.md)

## Context

ADR-0005 kept the LLM out of the trading path and gave it explanation, preference interpretation and
anomaly triage. It named Llama 3.3 70B on Groq as the default model. Two things changed when the LLM was
built.

1. **The model.** During integration, Groq answered `404 model_not_found` for
   `llama-3.3-70b-versatile` on this project's key. A hard-coded model name is a single point of failure.
2. **The explanation.** Every agent decision already carries a template message built from its own
   numbers, and that message is the record of truth. An LLM rewording the same facts would add latency
   and risk and no information. What a homeowner actually lacks is a way to ask questions: "why did I buy
   from the EB at 9 pm?", "how much have I saved?", "keep more charge tonight".

## Decision

The LLM becomes a **household advisor**: a chat on the dashboard that answers from the household's own
data (`app/agents/advisor.py`).

- **A LangGraph tool loop.** The model and the tools alternate for at most 4 tool rounds before the model
  must answer.
- **Five read tools:** `get_session`, `get_my_plan` (the forecast, the agent's decisions, and the battery
  and panel facts), `get_my_money`, `get_my_family_now` and `explain_hour`.
- **One write tool:** `set_reserve`, which changes only the caller's own battery reserve. The server
  enforces 10–90% itself rather than trusting the tool schema, because a model can ignore a schema. A call
  with no percent, or one outside that range, changes nothing and returns an error to the model.
- **The model is configuration.** The default is `GROQ_MODEL=openai/gpt-oss-120b`, called through an
  OpenAI-compatible client with retries. `LLM_PROVIDER` selects `groq`, `ollama` or `stub`.
- **Any provider error falls back to the stub,** which answers from the same tools without a model. The
  trading path never calls the advisor.
- The API key lives only in `.env`, which git ignores. CI uses the stub and needs no key.

## Consequences

**Good**

- Answers come from tool output, not the model's memory. One early hallucination, a battery the house
  did not have, was fixed by adding the battery and panel facts to `get_my_plan`.
- A preference stated in plain words ("keep 60% for tonight") becomes a validated, typed setting. This is
  the preference interpretation ADR-0005 promised.
- A Groq answer took about 3.4 s in Docker, acceptable for a chat and irrelevant to the market.

**Bad / accepted**

- An external dependency whose model names change. This record exists because one did.
- The LLM can change one setting. The change is bounded and audited, but it is no longer read-only.
- ADR-0005's anomaly triage for the operator is not built.
- The key used in development was pasted into a chat transcript and should be rotated.
