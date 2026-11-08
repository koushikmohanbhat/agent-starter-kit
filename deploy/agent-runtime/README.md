# Deploy to Google Cloud Agent Runtime

The managed-runtime path on Google Cloud (Agent Runtime on the Gemini Enterprise Agent Platform, which replaced
Vertex AI Agent Engine in 2026). `agent.py` wraps the kit runtime as a custom agent object with `set_up()` and
`query()`; ADK with Gemini is the natural adapter here (`AGENT_FRAMEWORK=adk`, `MODEL_PROVIDER=gemini`).

1. Copy your kit folder next to `agent.py` as `kit/`.
2. Deploy with the Agent Platform SDK (`agent_engines.create(...)` in the current SDK; see `agent.py`), with
   `requirements=["agent-starter-kit[adk,postgres]"]` and environment variables for the model and `SESSION_STORE`.
3. Sessions: point `SESSION_STORE` at Cloud SQL / AlloyDB so the API service (Cloud Run) and Agent Runtime share
   sessions and approvals; the approval endpoints are served by `kit serve`, not by Agent Runtime.

Status: implemented, not yet deployed live. If you only need a container, use Cloud Run (`../terraform/gcp-cloud-run`).
