# Security

- **Identity never comes from the model.** The service authenticates the caller (OIDC or API key) and passes the end
  user to tools in `ToolContext`. Tools filter by `ctx.user`; another customer's order looks like a missing one.
- **Policies run before every tool call**, in a sandboxed expression language (no attribute access to internals,
  no imports, no arbitrary calls). Denials are explained to the model; approvals hold the action for a person.
- **Prompt injection.** The model can be talked into calling a tool; it cannot change who the user is, skip a
  policy, or exceed the limits. The parity suite includes an injection attempt.
- **Limits:** tool calls per turn, turns, and a timeout per turn.
- **Sessions** are bound to one user and tenant. Approvals are bound to a tenant and a role.
- **Secrets:** inline secrets in `agent.yaml` are rejected; keys come from env vars set by the platform's secret
  store. `KIT_AUTH=dev` is refused unless `KIT_ENV=dev`.
- **Data:** message content is not written to traces unless `KIT_CAPTURE_CONTENT=true`, and then through the
  `redact` hook (the DPDP add-on tokenises it). `DELETE /v1/users/{id}` erases one user's sessions and approvals.
- **Code you add runs with the service's permissions:** tools, services and hooks are Python in your kit folder.
  Review them like application code.
- **Supply chain:** CI with CodeQL, Dependabot and pip-audit; framework extras pinned to tested ranges.

Report vulnerabilities privately through GitHub security advisories (see SECURITY.md).
