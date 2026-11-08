# DPDP add-on

Connects the agent to the [DPDP Data Rights Framework](https://github.com/koushikmohanbhat/dpdp-data-rights-framework):
messages are tokenised before any model sees them, processing stops when consent for the purpose is withdrawn,
conversations are registered as lineage artifacts, and `DELETE /v1/users/{id}` (role `privacy_admin`) erases one
customer's sessions and approvals so the framework's erasure orchestrator can call it as a connector.

1. Install the framework and write its config (see its docs): `DPDP_CONFIG=dpdp.yaml`, `DPDP_PURPOSE=customer_support`.
2. `kit add dpdp` has added a `hooks:` block to agent.yaml pointing at `dpdp_hooks.py`.
3. Register the kit as an erasure target in the framework: HTTP connector, `DELETE {AGENT_URL}/v1/users/{principal}`
   with a service identity that has the `privacy_admin` role.

Tools receive tokens. If a tool needs a real value (an address to send to the courier), reveal it through the
framework inside the tool, with the same purpose. Status: implemented against the framework's documented SDK; not
yet tested live.
