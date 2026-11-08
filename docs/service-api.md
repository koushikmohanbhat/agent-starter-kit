# Service API

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /v1/chat` | end user | `{message, session_id?, stream?}`. Returns `message`, `session_id`, `tool_calls`, `pending_approvals`, `usage`, `framework`, `model`, `prompt`, `trace_id`, `latency_ms` (and `state` in test mode). With `stream: true`, server-sent events: `tool_call`, `tool_result`, `approval_required`, `final`, `error` |
| `GET /v1/sessions/{id}` | owner | transcript |
| `DELETE /v1/sessions/{id}` | owner | delete a conversation |
| `GET /v1/approvals?status=pending` | approver role | approvals for your roles, in your tenant |
| `POST /v1/approvals/{id}` | approver role | `{approve: bool, reason?}` |
| `DELETE /v1/users/{user_id}` | `privacy_admin` | erase one end user's sessions and approvals in your tenant |
| `GET /v1/agent` | any | framework, model, prompt version, tools, policies, limits |
| `GET /healthz`, `/readyz` | none | liveness; readiness (session store reachable) |

Errors are `{"error": {"status", "message"}}` with 400 / 401 / 403 / 404 / 409 / 503.

## Auth (`KIT_AUTH`)

- `oidc`: `Authorization: Bearer <JWT>` validated against `KIT_OIDC_ISSUER` (JWKS at `<issuer>/.well-known/jwks.json`
  or `KIT_OIDC_JWKS_URL`) for `KIT_OIDC_AUDIENCE`. `sub` is the end user; roles from `KIT_OIDC_ROLES_CLAIM`
  (default `roles`), tenant from `KIT_OIDC_TENANT_CLAIM` (default `tenant`).
- `api_key`: a trusted backend sends `X-API-Key` and names the end user in `X-End-User-Id` (`X-End-User-Roles`,
  `X-Tenant`). Keys in `KIT_API_KEYS`, from a secret manager.
- `dev`: identity from `X-User-Id` / `X-User-Roles`, no checks; only with `KIT_ENV=dev` (`kit dev`).

Sessions belong to one user in one tenant: another user's session id starts a new session rather than continuing it.

## Test mode

`KIT_TEST_MODE=true` gives every session its own sandboxed services (fresh demo orders) and adds `state` (the turn's
outcome from `test_state`) to replies, for eval suites. Never enable it in production.
