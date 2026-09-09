# 3. Native JWT authentication instead of Keycloak

- **Status:** Accepted
- **Date:** 2026-09-09
- **Supersedes:** the "Authentication: Keycloak" row of the Zeroth Review stack

## Context

Keycloak is an excellent identity server, and the wrong tool here.

- It is a **JVM application needing roughly 1 GB of RAM** at rest. Docker Desktop on the development
  machine has 7.6 GiB for *all* containers, and every free hosting tier this project targets offers
  512 MB. Keycloak alone would end free deployment.
- Cold start is tens of seconds, which makes the test suite and CI markedly slower.
- Its configuration surface — realms, clients, mappers, flows — is large, and reproducing it across
  environments needs realm-export management that is its own maintenance burden.

What this project actually needs is narrow: a login endpoint, hashed passwords, short-lived access
tokens, refresh tokens, and three roles (`household`, `operator`, `admin`). There is no federation
requirement, no social login, no SAML, and no external identity provider to integrate with.

## Decision

Implement authentication directly in FastAPI:

- **OAuth2 password flow** with `PyJWT`, HS256, short-lived access tokens and rotating refresh tokens
- **Argon2id** password hashing via `argon2-cffi` (the current password-hashing competition winner)
- Role-based access control enforced through FastAPI dependencies
- Token revocation via a Redis deny-list keyed on `jti`

## Consequences

**Good**

- Roughly 200 lines, fully unit-testable, with no external service to run, seed or wait for.
- The stack fits in free-tier memory, and tests need no auth container.
- The security boundary is readable in one file rather than distributed across a realm export.

**Bad / accepted**

- We own this code. Auth bugs are our bugs — mitigated by using vetted libraries for the primitives
  (never hand-rolled crypto), enforcing RBAC in one dependency rather than per-route, and running
  CodeQL plus Trivy over it in CI.
- No SSO, SAML or social login. If a future requirement demands federation, this decision is revisited
  with a new ADR; the token-issuing surface is deliberately small enough to swap.
