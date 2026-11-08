# Evals for this agent (add-on)

Adapted from the GenAI Eval Framework's `tool-agent` pack: the same graders and gates, this kit's orders, and the
kit's approval rule (refunds over the limit are held for a support lead). It calls the kit's HTTP API, so the same
suite measures whichever framework and model the service runs.

```bash
pip install "agent-starter-kit[evals]"          # installs genai-eval-framework
# terminal 1: the service in test mode (sandboxed sessions, turn outcome in replies; never in production)
KIT_AUTH=api_key KIT_API_KEYS=dev-key KIT_TEST_MODE=true SESSION_STORE=memory:// kit serve . --port 8080
# terminal 2
AGENT_KIT_API_KEY=dev-key AGENT_KIT_EVAL_USER=cust-001 genai-evals run evals/suite.yaml --providers evals/providers.yaml --out out/evals
```

Open `out/evals/report.html` and `scorecard.html`. Compare frameworks or models by restarting the service with a
different `AGENT_FRAMEWORK` / `MODEL_PROVIDER` and running again, or use `genai-evals compare`. For real judges,
DPDP tokenisation of stored results, online checks on the kit's OTel spans and the release-gate workflow, see the
eval framework's docs. `ci/evals.yml` is a GitHub Actions job that runs this suite on every pull request.
