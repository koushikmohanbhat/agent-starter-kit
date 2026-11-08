# Add-ons

The kit runs without any add-on. Each adds files and configuration to your project; nothing in the kit imports them.

## Evals (`kit add evals`)

Adds `evals/`: an eval suite for this agent on the [GenAI Eval Framework](https://github.com/koushikmohanbhat/genai-eval-framework),
adapted from its `tool-agent` pack (same graders and gates, this kit's orders, and the approval rule). It calls the
kit's HTTP API, so the same suite measures whichever framework and model the service runs. Graders: task success
(the turn's outcome), correct tool arguments, lookup before acting, escalation, step budget, no broken promises
(judge panel), no PII in replies, latency. Gates include `critical_pass()` over approvals, other customers' orders
and the prompt-injection case.

```bash
pip install "agent-starter-kit[evals]"
KIT_AUTH=api_key KIT_API_KEYS=dev-key KIT_TEST_MODE=true SESSION_STORE=memory:// kit serve . --port 8080 &
AGENT_KIT_API_KEY=dev-key AGENT_KIT_EVAL_USER=cust-001 genai-evals run evals/suite.yaml --providers evals/providers.yaml --out out/evals
```

CI runs this end to end (offline). `evals/ci/evals.yml` is a GitHub Actions job for your repo.

## DPDP (`kit add dpdp`)

Adds `dpdp_hooks.py` and a `hooks:` block: messages are tokenised by the
[DPDP Data Rights Framework](https://github.com/koushikmohanbhat/dpdp-data-rights-framework) before any model sees
them, processing is refused (403) when consent for the purpose is withdrawn, conversations are registered as
lineage artifacts, and trace content is tokenised. Register `DELETE /v1/users/{principal}` as the agent's erasure
connector in the framework. Status: implemented against the framework's documented SDK; not yet tested live.

## Connectors (`kit add connectors`)

Adds an `mcp_tools:` source to `agent.yaml`, pointing at a profile of the
[connector hub](https://github.com/koushikmohanbhat/agent-connector-hub) (catalog 3.2): governed tools for Salesforce,
ServiceNow, SAP and your own APIs, with per-user downstream identity, approvals and audit.

```yaml
mcp_tools:
  - url: "${CONNECTOR_HUB_URL:-http://127.0.0.1:8000}/mcp/${CONNECTOR_HUB_PROFILE:-support-agent}"
    headers_env: {X-API-Key: CONNECTOR_HUB_API_KEY}
    forward_user: true        # X-End-User-Id / X-End-User-Roles / X-Tenant from the kit's verified user
    prefix: ""                # e.g. hub_, if names clash with local tools
    include: []               # only these tools
```

At start-up the kit lists the profile's tools and binds them like local tools, on every framework. Run the hub with
`HUB_AUTH=api_key` and the same key. The kit's policies apply first, then the hub's; a call the hub holds reaches the
model as `pending_approval` and is decided in the hub (`/v1/approvals`). Install with
`pip install 'agent-starter-kit[connectors]'`.

