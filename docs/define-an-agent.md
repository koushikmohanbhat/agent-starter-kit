# Define an agent

`agent.yaml` is the framework-neutral definition. Values can use `${VAR}` and `${VAR:-default}`; secrets are never
written in it (`api_key: ...` is rejected at load; use `api_key_env: <ENV_VAR>`).

| Key | Meaning |
|---|---|
| `name`, `description` | identifies the agent in spans, `/v1/agent` and logs |
| `framework` | `openai_agents` (default), `langgraph`, `adk`, `strands` |
| `model` | `provider` (`scripted`, `openai`, `openai_compatible`, `anthropic`, `bedrock`, `gemini`), `name`, `base_url`, `api_key_env`, `region`, `project`, `location`, `settings` (temperature, max_tokens), `script` (scripted model) |
| `instructions` | `{prompt: id, stage: prod}` (versioned, from `prompts/` and `prompts.lock`), `{prompt: id@1.2.0}`, or `{text: "..."}` |
| `tools` | `module:function` references, relative to the kit folder |
| `policies` | per tool: `deny_if`, `require_approval_if`, `approver_role`, `message` |
| `limits` | `max_turns`, `max_tool_calls` (per turn), `timeout_s` |
| `session` | `store` URL (`memory://`, `sqlite:///...`, `postgresql+psycopg://...`), `ttl_hours` |
| `services` | `name: module:factory`, objects tools get in `ctx.services` (e.g. the order client) |
| `test_state` | `module:fn(tool_calls) -> dict`, the outcome of a turn, returned only with `KIT_TEST_MODE=true` |
| `hooks` | `inbound`, `on_session_saved`, `redact`, `on_user_erased` (used by add-ons) |
| `mcp_tools` | tools listed from MCP servers at start-up, e.g. the connector hub (`kit add connectors`); needs the `connectors` extra |
| `escalation.approval_messages` | templates for what the customer is told when an approval is decided |

## Tools

```python
from agent_kit.tools import ToolContext

def issue_refund(order_id: str, amount: float, reason: str = "", *, ctx: ToolContext) -> dict:
    """Refund a delivered order, up to its total."""          # first paragraph = the model's description
    order = ctx.services["orders"].get(order_id, ctx.user.id)  # identity from ctx, not from the model
    ...
```

- The schema comes from the type hints (pydantic); `ctx` is hidden from the model.
- Return a dict (or a pydantic model). Exceptions become `{"status": "error", ...}` for the model, not crashes.
- Business rules that depend on data (delivered? already refunded?) belong in the tool. Rules about *who may do
  what at which size* belong in policies, so they hold whatever the model or framework does.

## Policies

Sandboxed expressions over `args` and `user` (`id`, `tenant`, `roles`): comparisons, `and`/`or`/`not`, `in`,
arithmetic, `len`/`lower`/`upper`. Anything else is rejected when the agent loads. `deny_if` wins over
`require_approval_if`; a missing argument makes a rule false rather than an error.

## Prompts

Immutable version folders (`prompts/<id>/<version>/system.md` or `system.md.j2` + `prompt.yaml`) and a
`prompts.lock` with a hash per version and a version per stage. Editing a locked version fails at load; create a
new version and `kit prompts promote <id> <version> --stage prod`. The same layout as the GenAI Eval Framework, so
its `prompts diff` can gate a prompt change.
