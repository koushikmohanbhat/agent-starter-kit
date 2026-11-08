# Framework adapters

Each adapter builds the framework's own agent from the definition and runs one turn. Tools reach every framework as
the same `BoundTool`s, so identity, policies, approvals, limits and tool events are identical; the framework's loop,
tool-call parsing and model client do the rest.

| Adapter (`AGENT_FRAMEWORK`) | Install | Built with | Models |
|---|---|---|---|
| `openai_agents` (default) | `[openai]` | `Agent`, `FunctionTool`, `Runner` | OpenAI via the Responses API; gateways via Chat Completions; Anthropic / Bedrock / Gemini via LiteLLM (`[litellm]`) |
| `langgraph` | `[langgraph]` | `StateGraph` (model ↔ `ToolNode`), LangChain chat models | `ChatOpenAI`; `ChatAnthropic` (`[anthropic]`); `ChatBedrockConverse` (`[bedrock]`); `ChatGoogleGenerativeAI` (`[gemini]`) |
| `adk` | `[adk]` (Python 3.11+) | `LlmAgent`, a neutral `BaseTool`, `Runner` | Gemini natively; others through ADK's LiteLLM model |
| `strands` | `[strands]` | `Agent`, `PythonAgentTool` | `BedrockModel`; `OpenAIModel`; `AnthropicModel`; LiteLLM for Gemini |

Pinned ranges: openai-agents 0.24.x (minor versions can break public APIs), langgraph 1.x, google-adk 2.x (2.0
changed storage and events), strands-agents 1.x. Upgrade one at a time and re-run the parity suite.

## Parity

`kit test --parity` runs `parity.yaml` on every installed adapter against the offline scripted model, which sits
behind an OpenAI-compatible endpoint so each framework uses its real HTTP model path. For each conversation it
checks the tool-call sequence, the final state of the kit's services, the approvals requested and a phrase in the
reply, and that adapters agree with each other. Add `--framework` to pick adapters and `--only` for one conversation.

What parity does not prove: that every framework behaves the same with a *real* model (sampling, tool-call
formatting and system-prompt handling differ). Use the evals add-on for that, per framework and model.

## Sessions

The kit's session store is the source of truth. Each turn passes the transcript (user and assistant text) to the
adapter; frameworks with their own session services (ADK) get an in-memory session rebuilt for the turn. Tool
calls and results inside a turn are kept in the session record but not replayed to the model.

## Adding an adapter

Implement `FrameworkAdapter.run(instructions, tools, history, message) -> AdapterResult` in
`agent_kit/adapters/<name>.py`, wrap each `BoundTool` in the framework's tool type (call `tool.call()` or
`tool.call_sync()`, nothing else), register it in `get_adapter`, and make the parity suite pass.
