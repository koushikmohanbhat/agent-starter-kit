# One image for every target (local, ECS Fargate, Cloud Run, Kubernetes, AgentCore Runtime).
#   docker build -t support-agent --build-arg EXTRAS=openai,postgres,otel --build-arg KIT=kits/support-agent .
# Pick the framework extras you deploy (openai | langgraph | adk | strands); all settings come from env at runtime.
FROM python:3.12-slim AS build
ARG EXTRAS=openai,postgres,otel
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY kits ./kits
COPY addon_files ./addon_files
COPY templates ./templates
RUN pip install --no-cache-dir --prefix=/install ".[${EXTRAS}]"

FROM python:3.12-slim
ARG KIT=kits/support-agent
RUN useradd --create-home --uid 10001 agent
COPY --from=build /install /usr/local
COPY --chown=agent:agent ${KIT} /app
USER agent
WORKDIR /app
ENV PORT=8080 PYTHONUNBUFFERED=1 KIT_DIR=/app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"
CMD ["sh", "-c", "kit serve /app --port ${PORT}"]
