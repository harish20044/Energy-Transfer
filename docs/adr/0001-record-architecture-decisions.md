# 1. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-09-09

## Context

The Zeroth Review proposed a tech stack before the system was designed in depth. Several of those
choices do not survive contact with production constraints, free-tier hosting, or the actual hardware
available. Changing them is correct, but a review panel will reasonably ask *why* — and "we changed it"
is a much weaker answer than a dated record of the trade-off that was weighed.

## Decision

Every architecturally significant decision — one that is costly to reverse, constrains future options,
or departs from the reviewed proposal — is recorded here as a numbered Architecture Decision Record, in
the format popularised by Michael Nygard: **Context**, **Decision**, **Consequences**, including the
consequences we dislike.

ADRs are immutable once accepted. A decision that is later reversed gets a new ADR that supersedes the
old one; the original stays in place so the reasoning history remains readable.

## Consequences

- Each departure from the reviewed proposal carries its own justification, which reads as engineering
  rigour rather than as scope drift.
- The thesis has a ready-made design-rationale chapter.
- Small ongoing cost: a decision is not finished until it is written down.
