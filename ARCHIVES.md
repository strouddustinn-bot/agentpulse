# AgentPulse Archives

Superseded implementations and recovery evidence are intentionally kept outside the production repository.

Local archive repository:

```text
/home/desktopdusty/workspace/repos/agentpulse-archives
```

It contains:

- a restorable Git bundle of all refs captured during consolidation;
- exact dirty working-tree patches from the protected original checkout;
- retired FastAPI, dashboard, deployment, observability, and test-harness snapshots;
- imported consolidation evidence and the original backup manifest;
- checksums and a source-disposition matrix.

Verify and restore locally:

```bash
cd /home/desktopdusty/workspace/repos/agentpulse-archives
sha256sum -c manifests/SHA256SUMS
git bundle verify bundles/agentpulse-all-refs-20260715.bundle
git clone bundles/agentpulse-all-refs-20260715.bundle /tmp/agentpulse-restored
```

This archive is intentionally local because no remote archive destination was authorized. A future remote publication must push the archive repository separately and record its immutable URL and revision here; cloning the active product repository alone does not retrieve local archive material.

The active master repository contains only the retained agent, Cloudflare Worker control plane, React console, shared contracts, configuration, scripts, and public documentation. Archive material must not be reintroduced without a new architecture decision and passing verification.
