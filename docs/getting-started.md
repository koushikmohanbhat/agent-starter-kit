# Getting started

```bash
pip install "agent-starter-kit[all] @ git+https://github.com/koushikmohanbhat/agent-starter-kit"
kit init my-agent            # copies kits/support-agent, plus .env.example and .gitignore
cd my-agent
kit check                    # definition, tools, policies, prompt and model settings
kit test --parity            # 12 conversations on all four frameworks, offline
kit run "Change the delivery address for ORD-10002 to 12 MG Road, Bengaluru 560001"
kit dev                      # local service + dev chat page at http://127.0.0.1:8080
```

Install only what you run: `agent-starter-kit[openai]`, `[langgraph]`, `[adk]` or `[strands]`, plus `[postgres]`,
`[otel]`, `[anthropic]`, `[bedrock]`, `[gemini]` as needed. `[all]` installs the four adapters, Postgres and OTel.

## From demo to a real deployment

| Step | Setting (in `.env` or the deploy environment) |
|---|---|
| Pick the framework | `AGENT_FRAMEWORK` |
| Pick the model | `MODEL_PROVIDER`, `MODEL_NAME` (+ the provider's credentials) |
| Connect the order system | `ORDER_API_URL`, `ORDER_API_TOKEN`, or your own client in `orders_client.py` |
| Identity | `KIT_AUTH=oidc` + `KIT_OIDC_ISSUER`, `KIT_OIDC_AUDIENCE` (or `api_key` + `KIT_API_KEYS`) |
| Sessions | `SESSION_STORE=postgresql+psycopg://...` |
| Approval limit | `REFUND_APPROVAL_LIMIT` |
| Telemetry | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME` |
| Deploy | [deploy.md](deploy.md) |
| Measure quality | `kit add evals` ([add-ons.md](add-ons.md)) |

`kit serve` refuses to start without `KIT_AUTH`, and dev auth is refused outside `KIT_ENV=dev`.

## Build your own agent

Copy the kit and change four things: the prompt (`prompts/`), the tools (`tools/`), the policies (`agent.yaml`) and
the parity conversations (`parity.yaml`). Write a scripted model for your domain if you want offline parity tests
(`scripted_model.py` shows the shape), or run parity against a real model with `MODEL_PROVIDER` set.
