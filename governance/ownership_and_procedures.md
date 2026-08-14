# Ownership, Authority, and Operational Procedures

## Ownership

- Model owner: ML Engineering Lead (responsible for model quality and release sign-off).
- Data owner: Data Platform Lead (responsible for source integrity, schema, and lineage).
- Approval authority: Operations Duty Manager (required approver for material field actions).

## Model Limitations

- Performance depends on timely and calibrated pressure/flow/demand telemetry.
- Elevated false alarms can occur during extreme seasonal demand anomalies.
- Detection confidence may degrade under unseen sensor failure modes.
- RAG guidance quality depends on corpus freshness and retrieval quality.

## Rollback Procedure

1. Execute rollback script to restore blue to 100 percent traffic.
2. Run endpoint smoke test and KPI sanity checks.
3. Freeze green promotion until root cause is documented.
4. Notify incident stakeholders and update change ticket.

Reference script:
- scripts/rollback_to_blue_v1.sh

## Retraining Procedure

1. Confirm retraining trigger from monitoring thresholds.
2. Refresh gold data and regenerate feature artifacts.
3. Run model suite training and scenario stress tests.
4. Re-evaluate production gate and data sufficiency checks.
5. Register candidate and deploy as green for blue/green validation.
6. Promote only after acceptance criteria and sign-off.

## Incident-Response Procedure

1. Capture alert details, timeline, and impacted services.
2. Assign incident commander and communication owner.
3. Determine if issue is endpoint, data, or model behavior.
4. Mitigate quickly (rollback, traffic shift, or fail-safe mode).
5. Preserve logs, traces, and payload samples for RCA.
6. Complete postmortem with action items and owners.
