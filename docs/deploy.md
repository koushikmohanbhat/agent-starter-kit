# Deploy

One image runs everywhere; all settings are environment variables. Pick the framework extras at build time:

```bash
docker build -t support-agent --build-arg EXTRAS=openai,postgres,otel .        # or langgraph / adk / strands
docker compose up --build                                                       # agent + Postgres + mock order API
```

| Target | Where | Status |
|---|---|---|
| Local / any container host | `Dockerfile`, `docker-compose.yml` | image built in CI |
| AWS, container | [`deploy/terraform/aws-ecs`](../deploy/terraform/aws-ecs): ECS Fargate, ALB (HTTPS), Secrets Manager, CloudWatch Logs, optional Bedrock invoke permissions | `terraform validate` in CI; not yet applied live |
| AWS, managed runtime | [`deploy/agentcore`](../deploy/agentcore): AgentCore Runtime entrypoint | implemented; not yet deployed |
| Google Cloud, container | [`deploy/terraform/gcp-cloud-run`](../deploy/terraform/gcp-cloud-run): Cloud Run, Secret Manager, service account, optional Gemini access | `terraform validate` in CI; not yet applied live |
| Google Cloud, managed runtime | [`deploy/agent-runtime`](../deploy/agent-runtime): Agent Runtime custom agent | implemented; not yet deployed |
| Kubernetes | the same image; a Helm chart is on the roadmap | – |

`kit deploy --print <target>` prints the target's steps.

## Production checklist

- `KIT_AUTH=oidc` (or `api_key` behind a trusted backend); never `dev`.
- `SESSION_STORE` on Postgres (RDS / Aurora / Cloud SQL / AlloyDB) when running more than one replica.
- Secrets from Secrets Manager / Secret Manager, injected as env vars by the platform.
- `KIT_TEST_MODE` unset.
- Telemetry exporter configured (`OTEL_EXPORTER_OTLP_ENDPOINT`; ADOT on AWS, the Telemetry API on Google Cloud).
- A pinned image tag and pinned framework extras; run `kit test --parity` and the evals before promoting.
