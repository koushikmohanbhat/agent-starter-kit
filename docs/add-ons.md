# Add-ons

The kit runs without either add-on. Each adds files and configuration to your project; nothing in the kit imports them.

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
