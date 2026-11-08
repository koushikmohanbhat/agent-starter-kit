# Deploy to Google Cloud: Cloud Run

1. Build and push to Artifact Registry (pick the framework extras you run, e.g. `adk,postgres,otel`):
   `gcloud builds submit --tag <region>-docker.pkg.dev/<project>/<repo>/support-agent:v1` (or docker build + push).
2. Create Secret Manager secrets (`SESSION_STORE` for Cloud SQL / AlloyDB Postgres, model or order API keys).
3. `cd deploy/terraform/gcp-cloud-run && cp terraform.tfvars.example terraform.tfvars`, fill it in, then
   `terraform init && terraform plan && terraform apply`.

Gemini on the Gemini Enterprise Agent Platform (formerly Vertex AI) uses the service account through ADC
(`use_gemini = true`). Telemetry: set `OTEL_EXPORTER_OTLP_ENDPOINT` to the Telemetry API or a collector.
Status: implemented, `terraform validate`d in CI; not yet applied in a live project.
