# Benchmark B0 / A2 / A4 / A5

Isolated from production `data`, Redis, Gold and the dashboard. Compose project:
`news-benchmark`; ports Kafka `19092`, PostgreSQL `15432` (loopback only).
The database password in Compose is a local benchmark fixture, not a production secret.

Preparation requires the existing local audit inputs
`data_artifacts/filter_review_20261117/full_review/reviewed_classified.parquet`
and `data_artifacts/extraction_review_20261117/after.parquet`. These article
datasets are intentionally not committed. `results/dataset_manifest.json` is the
small shareable provenance summary for the measured dataset.

```powershell
$env:PYTHONUTF8='1'
.venv/Scripts/python.exe benchmark/prepare.py
.venv/Scripts/python.exe -m pip install -r benchmark/requirements-report.txt
docker compose -f benchmark/compose.yaml up -d --build
docker compose -f benchmark/compose.yaml exec -T worker python check.py
.venv/Scripts/python.exe benchmark/run_suite.py --workloads T1 T2 --repeats 3
.venv/Scripts/python.exe benchmark/run_suite.py --workloads T3 --repeats 1
.venv/Scripts/python.exe benchmark/matching_python.py --repeats 3
.venv/Scripts/python.exe benchmark/report.py
```

To add only the current-stack baseline to existing recorded runs:

```powershell
docker compose -f benchmark/compose.yaml stop kafka
.venv/Scripts/python.exe benchmark/run_suite.py --architectures B0 --workloads T1 T2 --repeats 3
.venv/Scripts/python.exe benchmark/run_suite.py --architectures B0 --workloads T3 --repeats 1
docker compose -f benchmark/compose.yaml up -d --wait kafka
.venv/Scripts/python.exe benchmark/run_suite.py --architectures A2 --workloads T2 --repeats 1 --results-file baseline_control.csv
.venv/Scripts/python.exe benchmark/report.py
```

## Baseline B0

B0 uses Redis 7.4 with AOF/everysec (same server/settings as the main Compose),
the actual read-only-mounted `src/streaming/queue.py` ArticleQueue, one consumer,
LPUSH -> BRPOPLPUSH pending-to-processing -> commit DuckDB -> Lua ACK. Like the
current consumer, it commits one article per transaction. The production queue
source hash is recorded; no live Redis/Memurai namespace is touched.

This is the current **architecture/queue/commit scheduling** on the common
benchmark transform and compact output schema, not a full `ArticleProcessor`
execution. It excludes filtering/extraction/matching and their receipt schema,
just as the Kafka common-work benchmark does. It runs Redis in Docker/Linux,
not the Windows Memurai service. A2 uses up-to-512-row transactions, so B0/A2
differences include commit policy, not broker speed alone. A Redis LPUSH ACK with
AOF/everysec is not a per-message power-loss durability guarantee.

Resource scope for B0: worker + Redis + idle PostgreSQL. For A2/A4/A5: worker +
Kafka + PostgreSQL, preserving the previous resource scope. Redis and Kafka have
the same 2-CPU/1500m limits; worker limits/storage/input/SQL are unchanged. The
unused broker is not counted. `environment_*.json` preserve per-suite provenance;
the original `environment.json` and previous measurements are retained.

The real-Redis regression test claims a message, commits DuckDB, closes the
consumer before ACK, invokes production recovery, re-delivers and ACKs it, then
checks one row and empty pending/processing/dead queues. This remains a simulated
consumer-crash window, not a VM/power-failure recovery test.

Redis measurements buffer their commit ledger instead of flushing the Windows
bind mount after every article. The initial line-buffered Redis trials are
retained as `pilot_b0_linebuffered.csv`, excluded from the main comparison.
Original Kafka rows are retained; `baseline_control.csv` records a new A2/T2
control with buffered telemetry, separately from the original three-run median.

## Scope and fairness

- Real reviewed historical Silver, 20,745 unique articles, seven sources. They are
  **not 20,745 accidents**. `data/manifest.json` records counts and SHA256 provenance.
  Workloads use chronological prefixes of the same file, not balanced samples;
  the prefix source/label distribution may differ from the complete dataset.
- Both parsing and the deterministic Python/Polars transform run at benchmark
  time. Filtering/extraction are precomputed; event matching/embeddings are NOT
  executed. This follows the plan's common-work fallback; it does not benchmark
  RSS end-to-end or compare distributed matching algorithms.
- A2 Kafka Python consumer -> Polars -> one DuckDB writer; A4 Spark Kafka source
  -> `foreachBatch` -> same Polars transform -> PostgreSQL transaction; A5 same
  Spark path -> Delta transaction -> separate Parquet snapshot -> DuckDB query.
  A2 registers an Arrow batch and inserts with one SQL statement per transaction;
  preliminary row-wise INSERT timings are retained as pilots and excluded.
- Spark runs `local[1]` deliberately, one Kafka partition, same worker limit
  2 CPUs / 5 GiB, one-second trigger and max 512 input records per microbatch.
  All measured database/Delta/checkpoint/snapshot files use Docker Linux named
  volumes, not Windows/OneDrive bind mounts. Code, input and audit logs are bind-mounted.
  A2 accumulates up to 512 records for up to one second. Actual batch sizes differ
  with scheduling; throughput here includes producer pacing.
- Both Spark paths load the same Kafka/Delta dependencies and warm Spark before
  sending. Startup/package downloads are outside ingestion timing, but first
  Kafka microbatch and first storage initialization costs remain measured.
- Every run creates a new topic, consumer group, output path and checkpoint.
  PostgreSQL's isolated `benchmark.output` table is recreated before each A4 run.
  No simultaneous suite executions are permitted. Runs rotate order per repetition.
- The measured output stores article key, source, publication date, normalized
  title, SHA256 of title/description/content, precomputed facts/status, event ID
  (null), run ID and processing/send timestamps. It does not store the full body;
  storage/query results apply to this compact schema, not full-text archival.
- Kafka producer uses acks=all, retries and one in-flight request, so article order
  is preserved. Single-broker replication is **not** a high-availability test.

`matching_python.py` separately times the existing canonical Python matching
pipeline on 322 confirmed-scope articles with the default semantic model/config.
It prewarms the model and embedding cache, records warm-up time and fingerprint,
then runs three fresh private databases on the Windows host. Run it after the
architecture suite, never concurrently. This is reported separately, not added
to Kafka/storage throughput and not compared as a Spark matching measurement.

## Correctness and measurements

- Input and output keys/counts, duplicate count, missing count and deterministic
  fact digest are checked on every run. Timestamp/run IDs are excluded from the
  digest; facts are not. PostgreSQL/DuckDB key: `(run_id, article_key)`.
- Kafka offsets in A2 are committed only after DuckDB commit. Spark checkpoint
  advances after `foreachBatch` returns. Delta uses stable `txnAppId` + `txnVersion`.
- Re-execute the first committed batch after ingestion to test the duplicate
  delivery window. This is a sink retry test, **not a full process-kill/restart or
  infrastructure-failure test**. Such recovery remains an additional qualification.
- Latency is measured from `sent_at` immediately before producer send to wall
  clock observed immediately after storage commit returns. Producer and consumer
  use the same Linux VM clock. `processed_at` in output is not a commit timestamp;
  authoritative observed commits are in each run's `commits.jsonl`.
- Throughput = unique committed output / (last observed commit - first send).
  Drain = last observed commit - last send. CSV output has p50/p95 latency and
  duration. Kafka/network/queue/storage are all included.
- Resource sampling sums the active broker (Redis/Kafka) + PostgreSQL + worker (Python/JVM/producer)
  container Docker working-set RAM and CPU during ingestion. CPU 100% is one
  core; peaks are sampled, not exact continuous maxima. PostgreSQL stays running
  for all architectures. Docker VM overhead and unrelated host apps are excluded.
- A5's `snapshot_export_s` is measured separately from Delta ingestion; queries
  run on the exported snapshot. Do not add it to ingestion p95.
- Three identical SQL queries (sources, status, province/publication day article
  counts), warm once then 15 timed executions each. Query p95 is a pooled p95;
  per-query values/results are retained. They count articles, not incidents.
  Event count/top-event queries are omitted because input has no trustworthy
  event IDs for this workload; no fake event labels are produced.

## Artifacts and reset

- `results/runs.csv`, `summary.csv`, `report.md`: publishable numeric results.
- `results/environment.json`: hardware, image and limit evidence.
- `results/logs/`: raw process and resource logs (ignored by Git).
- `work/<run_id>/`: commits, checks, query results and metrics (ignored).
- `/storage/<run_id>/` in worker's named volume: DuckDB/Delta output,
  checkpoint and exported snapshot. PostgreSQL data has its own named volume.
- `data/`: input and manifest (ignored); original Silver is never overwritten.

Fresh run IDs provide a reset automatically. For explicit cleanup inside the
worker: `python reset.py <run_id>`. It only deletes that benchmark topic and its
isolated work directory, refuses active workloads, retains reports/logs. Kafka
consumer groups are per-run and never reused. To stop only this stack:
`docker compose -f benchmark/compose.yaml down`.

Official implementation references:
[Kafka Docker](https://kafka.apache.org/39/getting-started/docker/),
[Spark Kafka connector](https://spark.apache.org/docs/3.5.6/structured-streaming-kafka-integration.html),
[Delta idempotent foreachBatch](https://docs.delta.io/delta-streaming/),
[Spark/Delta compatibility](https://docs.delta.io/releases/).

Baseline references: [Redis reliable queue](https://redis.io/docs/latest/commands/rpoplpush/),
[Redis persistence](https://redis.io/docs/latest/management/persistence/).
