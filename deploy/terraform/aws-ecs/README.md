# Deploy to AWS: ECS Fargate behind an ALB

1. Build and push the image (pick the framework extras you run):
   ```bash
   docker build -t support-agent --build-arg EXTRAS=openai,postgres,otel .
   aws ecr create-repository --repository-name support-agent
   docker tag support-agent <account>.dkr.ecr.<region>.amazonaws.com/support-agent:v1 && docker push ...
   ```
2. Create secrets in Secrets Manager (model key, `SESSION_STORE` URL for RDS / Aurora Postgres, order API token).
3. `cd deploy/terraform/aws-ecs && cp terraform.tfvars.example terraform.tfvars`, fill it in, then
   `terraform init && terraform plan && terraform apply`.
4. Check `https://<alb>/readyz`, then call `/v1/chat` with a token from your identity provider.

For Bedrock models set `MODEL_PROVIDER=bedrock`, `MODEL_NAME` and `bedrock_model_arns` (the task role gets invoke
permissions only on those). Telemetry: run the ADOT collector as a sidecar or set `OTEL_EXPORTER_OTLP_ENDPOINT`.
Status: implemented, `terraform validate`d in CI; not yet applied in a live account.
