# Changelog

## 0.2.0 (2026-11-08)

- `mcp_tools` in `agent.yaml`: tools listed from MCP servers at start-up and bound like local tools on every
  framework, with the kit's user forwarded (`connectors` extra, MCP Python SDK 2.x).
- `kit add connectors`: wires a profile of the connector hub (agent-connector-hub) into the agent.
- Fix: policy rules could not read arguments named like dict methods (`args.items`, `args.keys`); those rules never
  fired.

## 0.1.0 (2026-11-08)

First release.

- Framework-neutral agent definition (`agent.yaml`): model, versioned instructions, typed tools, policies, limits,
  sessions, services, hooks; `${VAR}` interpolation; inline secrets rejected.
- Adapters for the OpenAI Agents SDK, LangGraph, Google ADK and Strands Agents.
- Tool boundary: identity in `ToolContext`, sandboxed policies (allow / deny / require approval), limits, events.
- Approvals: held tool calls, role- and tenant-checked decisions, execution with the original customer's identity,
  templated outcome messages.
- Service API: chat (JSON / SSE), sessions, approvals, user erasure, agent summary, health; OIDC, API key and dev auth.
- Stores: memory, SQLite, Postgres. OpenTelemetry GenAI spans on every adapter.
- Offline scripted model behind an OpenAI-compatible endpoint; parity suite (12 conversations × 4 frameworks).
- Support-agent kit with an order client, mock order API and dev chat page.
- Deploy: Dockerfile, Docker Compose, Terraform (ECS Fargate, Cloud Run), AgentCore Runtime and Agent Runtime wrappers.
- Add-ons: evals (GenAI Eval Framework suite for the kit) and DPDP hooks (DPDP Data Rights Framework).
