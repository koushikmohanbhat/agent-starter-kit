# Cloud Run service for the agent-starter-kit image. Environment-specific values are variables; secrets are
# Secret Manager secrets mounted as env vars. Ingress is public but every API call needs auth (KIT_AUTH).
terraform {
  required_version = ">= 1.6"
  required_providers { google = { source = "hashicorp/google", version = ">= 5.30" } }
}

provider "google" {
  project = var.project
  region  = var.region
}

variable "project" { type = string }
variable "region" { type = string }
variable "name" {
  type    = string
  default = "support-agent"
}
variable "image" { type = string }            # Artifact Registry image with tag
variable "environment" {
  type    = map(string)
  default = {}
}
variable "secrets" {                          # ENV_NAME => Secret Manager secret id (latest version is used)
  type    = map(string)
  default = {}
}
variable "use_gemini" {                       # grant the service account access to Gemini on the Agent Platform
  type    = bool
  default = false
}
variable "min_instances" {
  type    = number
  default = 0
}
variable "max_instances" {
  type    = number
  default = 10
}

resource "google_service_account" "agent" {
  account_id   = var.name
  display_name = "agent-starter-kit ${var.name}"
}

resource "google_project_iam_member" "gemini" {
  count   = var.use_gemini ? 1 : 0
  project = var.project
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_secret_manager_secret_iam_member" "access" {
  for_each  = var.secrets
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_cloud_run_v2_service" "agent" {
  name     = var.name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  template {
    service_account = google_service_account.agent.email
    timeout         = "120s"
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }
    containers {
      image = var.image
      ports { container_port = 8080 }
      dynamic "env" {
        for_each = merge({ GOOGLE_CLOUD_PROJECT = var.project, GOOGLE_CLOUD_LOCATION = var.region }, var.environment)
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = var.secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
      startup_probe {
        http_get { path = "/readyz" }
      }
    }
  }
  depends_on = [google_secret_manager_secret_iam_member.access]
}

# Cloud Run authenticates nothing here: the service enforces KIT_AUTH (oidc / api_key) itself.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.agent.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "url" { value = google_cloud_run_v2_service.agent.uri }
