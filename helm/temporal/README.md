# Temporal control plane chart

This wrapper pins the upstream Temporal server chart and deliberately has no
deployable defaults. It is the durable-workflow engine for the control plane,
not a replacement for application state or immutable audit evidence.

Before any release, an approved private runner must verify all of the following:

1. PostgreSQL Flexible Server is private, TLS-enforced, backed up, and has the
   `temporal` and `temporal_visibility` databases.
2. A least-privilege Temporal database user exists; its password has been
   delivered to a pre-created Kubernetes Secret through the approved secret
   delivery path. It is never supplied with `--set` or committed in values.
3. The reviewed migration run has completed before the normal server release.
   This chart keeps both `createDatabase` and `manageSchema` disabled.
4. The release uses a private AKS runner, fixed chart version, resource limits,
   disruption budgets, monitoring, backup/restore drill, and audit evidence.

`values.ci.yaml` is for rendering only and must never be deployed.
