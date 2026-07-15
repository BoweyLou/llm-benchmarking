# Proxmox Tailnet LLM Model Tool Deployment

The LLM Model Tool can run as a private FastAPI service on the
Proxmox host and bind only to the host's Tailscale IPv4 address.

## Deploy

From the repository root:

```bash
scripts/deploy_proxmox_review_workbench.sh
```

Defaults:

- SSH host: `proxmox`
- Service URL: `http://<proxmox-tailscale-ip>:8766/review`
- App checkout: `/opt/llm-benchmarking/current`
- Persistent SQLite database: `/var/lib/llm-benchmarking/db.sqlite`
- Systemd unit: `/etc/systemd/system/llm-benchmarking.service`
- Environment file: `/etc/llm-benchmarking.env`
- Runtime user: `llm-benchmarking`
- Trusted tailnet writes: enabled with
  `LLM_BENCHMARKING_TRUSTED_TAILNET_WRITES=1`

Set `REMOTE_HOST`, `REMOTE_PORT`, `TAILSCALE_IP`,
`TAILNET_TRUSTED_WRITES`, or `ADMIN_TOKEN` in the local environment when a
deploy needs different connection details, tokenless-write behavior, or a
preselected admin token:

```bash
ADMIN_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)" scripts/deploy_proxmox_review_workbench.sh
```

The first deploy seeds the remote persistent database from local `data/db.sqlite`
when that file exists. Later deploys preserve the remote database and token
fallback so manual review decisions survive code updates.

On Debian-based Proxmox hosts, the script installs `python3-venv` or the
matching versioned package, such as `python3.11-venv`, if the base Python
runtime cannot create a virtual environment.

## Refresh Benchmark Evidence

The deploy preserves `/var/lib/llm-benchmarking/db.sqlite`; deploying code alone
does not replace existing benchmark rows. After deploying the benchmark
comparison release, run a targeted SWE-bench and MTEB refresh on the host. This
replaces legacy invalid SWE-bench values and repopulates MTEB from the complete
deterministic model/task enumeration, with no per-model or global task cap:

```bash
ssh proxmox '
  cd /opt/llm-benchmarking/current
  set -a
  . /etc/llm-benchmarking.env
  set +a
  .venv/bin/python -m backend update --benchmarks \
    swebench_verified swebench_full swebench_lite \
    swebench_multilingual swebench_multimodal \
    mteb_retrieval mteb_reranking \
    mteb_retrieval_reranking rteb_finance
'
ssh proxmox "systemctl restart llm-benchmarking.service"
```

The browser's `Run updates` action can perform a full refresh instead. Keep the
targeted command for a controlled rollout and for proving the repaired source
coverage without mixing unrelated adapters into the verification run. Review
the update log before continuing: both adapters must finish successfully,
`probe_complete` must be true, selected MTEB requested and fetched task-file
totals must agree, and later-listed models must produce evidence when they have
accessible eligible task files. The probed total must reconcile to accessible
plus explicitly stale (`404`/`410`) paths; every other failed-task count must be
zero. MTEB chooses a coherent accessible revision deterministically, records
split/subset signatures, and retries transient failures with backoff. RTEB must
show seven completed tasks, whether its mode is `dataset_server` or the bounded,
revision-pinned `parquet_fallback`. Any unresolved partial task, fallback shard,
or RTEB row fails closed; the prior scores remain active and the rollout must
stop rather than accepting a partial refresh.

## Use

Open the LLM Model Tool from any device on the tailnet:

```text
http://<proxmox-tailscale-ip>:8766/review
```

Devices on the Tailscale network can browse and save decisions without pasting
an admin token. The service still keeps an admin-token fallback for non-tailnet
operations or if trusted tailnet writes are disabled:

```bash
ssh proxmox "sed -n 's/^LLM_BENCHMARKING_ADMIN_TOKEN=//p' /etc/llm-benchmarking.env"
```

## Verify the Comparison Release

Set the tailnet base URL locally, then inspect the public contracts:

```bash
BASE_URL="http://<proxmox-tailscale-ip>:8766"
curl -fsS "$BASE_URL/api/benchmarks" > /tmp/lbm-073-benchmarks.json
curl -fsS "$BASE_URL/api/models" > /tmp/lbm-073-models.json
curl -fsS "$BASE_URL/api/review/catalog" > /tmp/lbm-073-review.json
curl -fsS "$BASE_URL/api/rankings?use_case=retrieval_embeddings" > /tmp/lbm-073-rankings.json
```

Verify the following before treating the rollout as complete:

- `/api/benchmarks` exposes exactly the 92 code-owned active benchmark policies
  and aggregate distributions; no active definition is missing or duplicated.
  A retired database-only definition is inactive while its historical scores
  remain stored.
- `/api/review/catalog` reports schema version 4. Every non-null score exposes
  `display` plus `comparison.status`, strict and broad cohorts, coverage,
  evidence depth, warnings, and `as_of`.
- Large catalog responses support standard gzip content encoding; measure both
  compressed transfer bytes/time and the decoded contract size during rollout.
- An embedding model shows strict MTEB context and broader same-role context;
  mixed task sets or configurations are labelled rather than presented as
  directly comparable. Confirm coherent revision, split, and subset signatures
  in the refreshed score metadata.
- A lower-is-better metric, such as ASR word error rate, shows the correct
  direction. WER above 100 remains valid, while invalid bounded values are
  marked for a data check and excluded from cohorts.
- Refreshed SWE-bench values remain percentage points: an upstream `1.4`
  appears as `1.4%`, never `140%`. MTEB database coverage includes models from
  beyond the old source-order truncation boundary.
- Ranking breakdowns carry benchmark comparison context without changing the
  weighted use-case score, and generated JSON/JSONL, clean CSV, normalized
  score CSV, raw CSV, and banking exports retain their documented fields.
  Values that render identically at display precision remain separately ranked
  unless their stored normalized numeric values are equal. The normalized score
  sidecar and model-level counts include an exact latest configured observation
  once even when compatibility fields expose it in both score collections.
- `/review` shows four relevance-selected Key benchmarks, an accessible
  expandable complete list, missing-relevant-evidence states, and wording that
  distinguishes Verified source provenance from independent reproduction or
  production approval. Missing evidence must follow the active use case's
  positive weights and required benchmarks before falling back to role defaults.
  Check populated and empty states on both desktop and a narrow mobile viewport.

## Operate

Check the service:

```bash
ssh proxmox "systemctl status llm-benchmarking.service --no-pager"
```

Read recent logs:

```bash
ssh proxmox "journalctl -u llm-benchmarking.service -n 100 --no-pager"
```

Restart after manual environment changes:

```bash
ssh proxmox "systemctl restart llm-benchmarking.service"
```

Back up review decisions before rebuilding the database by using the LLM Model Tool
snapshot export, or by copying `/var/lib/llm-benchmarking/db.sqlite` from the
Proxmox host.
