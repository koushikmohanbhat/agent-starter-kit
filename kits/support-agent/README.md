# Support-agent kit

A customer-support agent for an online store: order status, refunds, address changes and escalation to a person.

| Tool | Rule | Where it's enforced |
|---|---|---|
| `lookup_order` | only the signed-in customer's orders; anyone else's looks "not found" | tool (from `ctx.user`) |
| `issue_refund` | delivered orders only, at most the total, once | tool |
| `issue_refund` | above `REFUND_APPROVAL_LIMIT` (default ₹5,000) needs a `support_lead` | policy in `agent.yaml` |
| `update_address` | only before shipping | tool |
| `escalate_to_human` | always available | – |

## Files

| | |
|---|---|
| `agent.yaml` | the definition (framework, model, prompt, tools, policies, limits, sessions, services) |
| `prompts/support_agent/1.0.0/` + `prompts.lock` | versioned instructions; `kit prompts lock` / `promote` |
| `tools/` | the four tools (typed functions) |
| `orders_client.py` | the order system: in-memory demo data, or HTTP (`ORDER_API_URL`) |
| `mock_api/app.py` | a mock order API with the routes `HttpOrders` calls |
| `scripted_model.py` | the offline model used by tests, demos and the parity suite |
| `parity.yaml` | 12 conversations every framework adapter must agree on |
| `data/orders.json` | demo orders for customers `cust-001` and `cust-002` |

## Connect real systems

1. **A model.** In `.env`: `MODEL_PROVIDER=openai` and `MODEL_NAME=<model>` (plus `OPENAI_API_KEY`). Or `anthropic`,
   `bedrock` (`AWS_REGION`), `gemini` (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`), or `openai_compatible`
   (`MODEL_BASE_URL`, `MODEL_API_KEY_ENV`) for a gateway. Then `kit run "Where is ORD-10003?"`.
2. **The framework.** `AGENT_FRAMEWORK=openai_agents | langgraph | adk | strands` and install the matching extra.
3. **The order system.** Either implement the five methods of `InMemoryOrders` against the customer's API, or put a
   facade with the mock API's routes in front of it and set `ORDER_API_URL` (+ `ORDER_API_TOKEN`).
4. **Identity.** `KIT_AUTH=oidc` with the customer's IdP (`KIT_OIDC_ISSUER`, `KIT_OIDC_AUDIENCE`), or `api_key`
   when a trusted backend calls on the customer's behalf.
5. **Sessions.** `SESSION_STORE=postgresql+psycopg://...` for more than one replica.
6. Re-run `kit test --parity` after changing tools or the prompt (offline), then the evals add-on with the real model.
