# Blue Green Release Runbook (AML CLI v1)

## 1) Create Green Candidate Deployment

Run:

```bash
./scripts/deploy_green_candidate_v1.sh
```

Defaults:
- Deploys version `green`
- Routes limited traffic (`GREEN_TRAFFIC_PERCENTILE`, default 10)

## 2) Run Blue/Green Testing

Compare deterministic output differences by forcing traffic to blue then green:

```bash
./scripts/blue_green_compare_v1.sh | tee blue_green_compare.json
```

## 3) Route Limited Traffic To Green

The green deployment script already supports limited rollout. Example 5%:

```bash
GREEN_TRAFFIC_PERCENTILE=5 ./scripts/deploy_green_candidate_v1.sh
```

## 4) Compare Blue vs Green

Use comparison output metrics:
- `mean_score_delta`
- `max_score_delta`

## 5) Validate Rollback

```bash
./scripts/rollback_to_blue_v1.sh
./scripts/smoke_test_realtime_endpoint_v1.sh
```

## 6) Promote Green Only After Acceptance Criteria

```bash
COMPARE_REPORT=blue_green_compare.json \
MAX_MEAN_SCORE_DELTA=0.08 \
MAX_MAX_SCORE_DELTA=0.20 \
./scripts/promote_green_v1.sh
```

If acceptance criteria fail, promotion script exits non-zero and does not change traffic.

## 7) Post-Promotion Smoke + Load Test

```bash
./scripts/smoke_test_realtime_endpoint_v1.sh
python scripts/load_test_endpoint.py --url http://localhost:8000/predict --requests 300 --concurrency 30
```

## Note Summary

This runbook defines the controlled transition from a known-good blue deployment to a candidate green deployment. The purpose is to reduce release risk by validating score stability, limiting rollout exposure, and preserving a safe rollback path if the new version fails a production gate.

The promotion decision is:

$$
\text{Promote Green} = \left(\Delta \text{Mean Score} \leq \theta_1\right) \land \left(\Delta \text{Max Score} \leq \theta_2\right) \land \left(\text{Smoke Test Passed}\right)
$$

Where $\theta_1$ and $\theta_2$ are the acceptance thresholds defined in the deployment gate. If the observed deltas exceed those limits, the rollout remains only for evaluation or reverts immediately to blue.
