# AML CLI v1 Realtime Endpoint Operations

This workspace currently uses Azure ML CLI v1 (`az ml endpoint realtime ...`).
The v2-style commands (`az ml online-endpoint`, `az ml online-deployment`) are not available in this environment.

## 1) Deploy Or Update Blue Version

Use the script below to create or update the `blue` version for the realtime endpoint.

```bash
./scripts/deploy_realtime_endpoint_v1.sh
```

Common overrides:

```bash
WORKSPACE_NAME=WSVelaqua \
RESOURCE_GROUP=Velaqua \
ENDPOINT_NAME=water-intel-online \
VERSION_NAME=blue \
MODEL_NAME=water-leak-production-candidate \
MODEL_VERSION=3 \
ENV_NAME=water-intel-training-env \
ENV_VERSION=1 \
./scripts/deploy_realtime_endpoint_v1.sh
```

Notes:
- The script resolves `MODEL_ID` automatically from latest model version when not provided.
- It uses `create-version`, then falls back to `update-version` for idempotent reruns.
- It enforces endpoint auth posture via `token auth`, `key auth`, and `App Insights` flags.

## 2) Smoke Test Inference

```bash
./scripts/smoke_test_realtime_endpoint_v1.sh
```

Override payload and endpoint as needed:

```bash
ENDPOINT_NAME=water-intel-online \
INPUT_DATA=ml/deployment/smoke_payload.json \
./scripts/smoke_test_realtime_endpoint_v1.sh
```

## 3) Authentication Guidance

Prefer Entra token auth for production callers.

```bash
az ml endpoint realtime get-access-token -w WSVelaqua -g Velaqua -n water-intel-online
```

Key auth should remain enabled only for controlled integration scenarios.
Rotate keys periodically:

```bash
az ml endpoint realtime regen-key -w WSVelaqua -g Velaqua -n water-intel-online --key-type Primary
```

## 4) Managed Identity, RBAC, and Key Vault

- Use system-assigned managed identity for API and automation workloads.
- Grant least-privilege RBAC:
  - `AzureML Data Scientist` for model lifecycle workflows.
  - `AzureML Compute Operator` only where compute mutation is required.
  - Key Vault `Secrets User` on read paths only.
- Keep secrets out of source control and read from Key Vault or environment variables injected at deploy time.

## 5) APIM Front Door Pattern

Recommended production path:

1. APIM inbound policy validates Entra JWT and optional subscription key.
2. APIM injects trace headers (`x-request-id`, correlation id).
3. APIM forwards to decision API private backend.
4. Decision API calls AML endpoint and RAG service using managed identity.
5. APIM applies throttling and response caching policies where safe.

## 6) Operational Controls

- Health endpoint: `/health`
- Readiness endpoint: `/ready`
- Request tracing: response `x-request-id` propagated by API middleware.
- Basic API rate limit: configured with `RATE_LIMIT_WINDOW_SECONDS` and `RATE_LIMIT_MAX_REQUESTS`.
- RAG timeout and retries: `RAG_TIMEOUT_SECONDS`, `RAG_MAX_RETRIES`.

## 7) Migration Reminder

Azure ML CLI v1 is in retirement window. Keep these scripts as compatibility shims and plan migration to CLI v2 managed online endpoints.

## Note Summary

This endpoint operations guide defines the control conditions for a production realtime model. The objective is to keep serving latency low, request handling reliable, and authentication posture compliant while preserving a clear rollback path and safe promotion workflow.

The serving health objective is:

$$
\text{Serving Health} = \text{Availability} \land \text{Auth Compliance} \land \text{Latency SLO} \land \text{Rollback Readiness}
$$

The operational performance target is:

$$
\text{P95 Latency} < \text{SLO Threshold}
$$

and

$$
\text{Error Rate} = \frac{\text{Failed Requests}}{\text{Total Requests}} \ll 1
$$

This ensures the realtime endpoint remains healthy enough for critical leak detection decisions without exposing unsafe or ungoverned access paths.