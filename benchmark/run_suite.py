"""Host orchestration, real container-wide resource sampling, serial workloads."""
import argparse
import csv
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import threading
import time
import uuid

BASE = Path(__file__).resolve().parent
COMPOSE = ["docker", "compose", "-f", str(BASE / "compose.yaml")]


def memory_mb(value):
    number, unit = value.split(" / ")[0].split() if " " in value.split(" / ")[0] else (None, None)
    if number is None:
        import re
        number, unit = re.fullmatch(r"([\d.]+)(\w+)", value.split(" / ")[0]).groups()
    factor = {"B": 1 / 1048576, "kB": 1000 / 1048576, "KB": 1000 / 1048576,
              "KiB": 1 / 1024, "MB": 1000000 / 1048576, "MiB": 1,
              "GB": 1000000000 / 1048576, "GiB": 1024}
    return float(number) * factor[unit]


def collect_resources(run_id, stop, samples, architecture):
    while not stop.is_set():
        try:
            phase = json.loads((BASE / "work/phase.json").read_text(encoding="utf-8"))
            if phase.get("run_id") == run_id and phase.get("active"):
                command = ["docker", "stats", "--no-stream", "--format", "{{json .}}",
                           "news-benchmark-redis-1" if architecture == "B0" else "news-benchmark-kafka-1",
                           "news-benchmark-postgres-1", "news-benchmark-worker-1"]
                response = subprocess.run(command, capture_output=True, text=True, timeout=20)
                if response.returncode:
                    raise RuntimeError(response.stderr)
                rows = [json.loads(line) for line in response.stdout.splitlines() if line.strip()]
                if len(rows) == 3:
                    samples.append({"time": time.time(), "ram_mb": sum(memory_mb(r["MemUsage"]) for r in rows),
                                    "cpu_pct": sum(float(r["CPUPerc"].strip("%")) for r in rows), "containers": rows})
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
            pass
        stop.wait(.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--architectures", nargs="+", default=["B0", "A2", "A4", "A5"], choices=["B0", "A2", "A4", "A5"])
    parser.add_argument("--workloads", nargs="+", default=["T1", "T2"], choices=["smoke", "T1", "T2", "T3"])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--results-file", default="runs.csv")
    args = parser.parse_args()
    if Path(args.results_file).name != args.results_file or not args.results_file.endswith(".csv"):
        parser.error("results-file must be a simple CSV filename")
    results = BASE / "results"
    logs = results / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    # Persist actual daemon hardware/versions and effective container limits.
    metadata = {"created_at": datetime.now(timezone.utc).isoformat(), "architectures": args.architectures,
                "results_file": args.results_file,
                "resource_scope": "sum of worker + active broker (Redis for B0, Kafka otherwise) + idle PostgreSQL during ingestion; Docker working-set memory; CPU 100%=one core; sampling ~1.5-3 seconds"}
    metadata["implementation_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                         for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".txt", ".yaml") or path.name == "Dockerfile"}
    metadata["production_queue_sha256"] = hashlib.sha256((BASE.parent / "src/streaming/queue.py").read_bytes()).hexdigest()
    for name, command in {"docker_info": ["docker", "info", "--format", "{{json .}}"],
                          "compose_config": COMPOSE + ["config", "--format", "json"],
                          "images": COMPOSE + ["images", "--format", "json"],
                          "pip_freeze": COMPOSE + ["exec", "-T", "worker", "pip", "freeze"],
                          "worker_mounts": ["docker", "inspect", "news-benchmark-worker-1", "--format", "{{json .Mounts}}"]}.items():
        response = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        metadata[name] = response.stdout
    environment = results / f"environment_{'-'.join(args.architectures).lower()}_{datetime.now():%Y%m%d_%H%M%S}.json"
    environment.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if not (results / "environment.json").exists():
        (results / "environment.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    for repeat in range(args.repeats):
        for workload in args.workloads:
            # Rotate execution order between repetitions to reduce cache/order bias.
            order = args.architectures[repeat % len(args.architectures):] + args.architectures[:repeat % len(args.architectures)]
            for architecture in order:
                run_id = f"{architecture.lower()}-{workload.lower()}-{datetime.now():%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
                print(f"START {run_id}", flush=True)
                stop, samples = threading.Event(), []
                monitor = threading.Thread(target=collect_resources, args=(run_id, stop, samples, architecture), daemon=True)
                monitor.start()
                with (logs / f"{run_id}.log").open("w", encoding="utf-8") as log:
                    process = subprocess.run(COMPOSE + ["exec", "-T", "worker", "python", "runner.py", architecture, workload, run_id],
                                             stdout=log, stderr=subprocess.STDOUT)
                stop.set()
                monitor.join(timeout=25)
                (logs / f"{run_id}.resources.json").write_text(json.dumps(samples), encoding="utf-8")
                if process.returncode:
                    print(f"FAILED {run_id}; see {logs / (run_id + '.log')}", flush=True)
                    raise SystemExit(process.returncode)
                metrics = json.loads((BASE / "work" / run_id / "metrics.json").read_text(encoding="utf-8"))
                if not samples:
                    raise RuntimeError("No resource samples; refuse to invent RAM/CPU")
                metrics["peak_ram_mb"] = max(r["ram_mb"] for r in samples)
                metrics["avg_cpu_pct"] = sum(r["cpu_pct"] for r in samples) / len(samples)
                metrics["resource_samples"] = len(samples)
                path = results / args.results_file
                exists = path.exists()
                if exists:
                    with path.open(encoding="utf-8", newline="") as source:
                        fieldnames = next(csv.reader(source))
                    assert set(fieldnames) == set(metrics)
                else:
                    fieldnames = list(metrics)
                with path.open("a", encoding="utf-8", newline="") as output:
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    if not exists:
                        writer.writeheader()
                    writer.writerow(metrics)
                print(f"DONE {run_id}: {metrics['output_count']} committed; {metrics['throughput_articles_s']:.2f} articles/s; p95 {metrics['latency_p95_ms']:.1f} ms", flush=True)


if __name__ == "__main__":
    import socket
    # OS releases the lock on process exit, including interrupted runs.
    with socket.socket() as suite_lock:
        suite_lock.bind(("127.0.0.1", 19666))
        main()
