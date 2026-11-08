# Deploy to Amazon Bedrock AgentCore Runtime

The managed-runtime path on AWS. Same agent definition and adapters; `entrypoint.py` adapts the kit runtime to
AgentCore's invoke contract (payload `{"prompt", "user_id"}`, AgentCore-managed sessions).

1. Build an image from the repo `Dockerfile` with `EXTRAS=openai,postgres,otel` (or `strands`, ...) plus
   `bedrock-agentcore`, and override the command: `python /app/deploy/agentcore/entrypoint.py` (copy this folder
   into the image, or build `FROM` the kit image). AgentCore expects an ARM64 image listening on port 8080.
2. Create the runtime with the AgentCore CLI or `bedrock-agentcore-control:CreateAgentRuntime`, pointing at the
   image in ECR and an execution role (CloudWatch Logs, Bedrock invoke on your models, Secrets Manager reads).
3. For end-user identity, configure an inbound JWT authorizer (AgentCore Identity) and pass the verified subject
   as `user_id`. Observability: AgentCore Runtime instruments with ADOT; the kit's spans join the same traces.

Approvals: AgentCore Runtime only exposes invoke. Point `SESSION_STORE` at a shared Postgres and run the API service
(`kit serve`) or a small ops service for `/v1/approvals`. Status: implemented, not yet deployed live.
