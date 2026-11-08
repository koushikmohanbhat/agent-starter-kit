# Approvals

A policy with `require_approval_if` holds a tool call for a person with the `approver_role`:

```yaml
policies:
  - {tool: issue_refund, require_approval_if: "args.amount > 5000", approver_role: support_lead}
```

1. The model calls the tool. The policy matches, so the tool does **not** run; the model gets
   `{"status": "pending_approval", "approval_id": ...}` and tells the customer it is under review.
2. The approval is stored with the arguments, the customer's identity, the session and the reason.
3. An approver lists `GET /v1/approvals` and decides with `POST /v1/approvals/{id}` `{approve, reason}`. Only users
   with the role, in the same tenant, can decide; each approval can be decided once.
4. On approve, the kit runs the held tool call with the **original customer's** identity (so record-level access
   still applies), records the result, and adds a templated message to the customer's session
   (`escalation.approval_messages`). On reject, nothing runs and the customer is told why.

This works the same on every framework, because it is enforced at the tool boundary rather than with each
framework's interrupt feature, and it holds when the model is manipulated: the parity suite includes a prompt
injection that asks for the refund "without approval", and the refund is still held.

The outcome message is a template, not model output, so what the customer is told is exactly what happened.
