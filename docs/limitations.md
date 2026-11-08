# Limitations (v0.1.0)

**Live-tested today: nothing.** Every adapter is parity tested with the offline scripted model through the
framework's real OpenAI-compatible model path. Real models (OpenAI, Anthropic, Bedrock, Gemini) through each
adapter, a real OIDC provider, Postgres, both Terraform modules, and the AgentCore Runtime and Agent Runtime
wrappers are implemented but have not been run against live services. The first live run in a partner sandbox is
the most useful contribution; please open an issue with what you find.

- **Parity is not equivalence with real models.** Frameworks differ in how they format tools and system prompts and
  how they retry; with a real model, the same definition can behave differently per framework. Measure with the
  evals add-on per framework and model.
- **One agent, no handoffs.** Escalation is a tool, not a handoff to another agent. Multi-agent kits are on the roadmap.
- **History is text only.** Earlier turns are replayed as user / assistant text; tool calls from earlier turns are
  not replayed to the model.
- **Streaming is event-level** (tool calls, approvals, final message), not token-by-token.
- **Approvals are decided through the API service.** The managed-runtime wrappers expose only invoke; run the API
  service against the same session store for approvals.
- **Python only.** TypeScript, voice and an MCP server for the tools are on the roadmap.
- The Agent Runtime SDK entry point moved with Google's platform rename; check the current module name.
