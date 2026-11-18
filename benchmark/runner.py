"""One real Kafka workload, executed inside the isolated benchmark worker."""
import argparse
import csv
import json
from pathlib import Path
import threading
import time

from kafka import KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic

from common import transform, digest, percentile, QUERIES
from producer import produce
from sinks import SqlSink, DeltaSink


def spark_session():
    from pyspark.sql import SparkSession
    from delta import configure_spark_with_delta_pip
    builder = (SparkSession.builder.master("local[1]").appName("news-benchmark")
               .config("spark.driver.memory", "2g")
               .config("spark.sql.shuffle.partitions", "1")
               .config("spark.default.parallelism", "1")
               .config("spark.ui.enabled", "false")
               .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
               .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog"))
    spark = configure_spark_with_delta_pip(builder, extra_packages=["org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.6"]).getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    spark.range(10).count()
    return spark


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("architecture", choices=["B0", "A2", "A4", "A5"])
    parser.add_argument("workload", choices=["smoke", "T1", "T2", "T3"])
    parser.add_argument("run_id")
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    number, rate = {"smoke": (100, 10), "T1": (1000, 50), "T2": (10000, 200), "T3": (20000, 0)}[args.workload]
    base = Path(__file__).resolve().parent
    work = base / "work" / args.run_id
    work.mkdir(parents=True, exist_ok=False)
    storage = Path("/storage") / args.run_id
    storage.mkdir(parents=True, exist_ok=False)
    with (base / "data/articles.jsonl").open(encoding="utf-8") as stream:
        rows = [json.loads(next(stream)) for _ in range(number)]
    assert len({r["article_key"] for r in rows}) == number
    topic = "bench-" + args.run_id.lower().replace("_", "-")
    admin = None
    if args.architecture != "B0":
        admin = KafkaAdminClient(bootstrap_servers="kafka:9092")
        admin.create_topics([NewTopic(topic, 1, 1)])
    state, committed, batches, first_batch = {}, {}, [], []
    spark, query, consumer = None, None, None
    sink = None
    phase = base / "work/phase.json"
    # Buffer telemetry, especially for per-article B0 commits. Flushing a Windows
    # bind mount on every record otherwise measures logging rather than storage.
    log = (work / "commits.jsonl").open("w", encoding="utf-8", buffering=1024 * 1024)
    def commit(raw, batch_id):
        if not raw:
            return
        output = transform(raw)
        if len({r["article_key"] for r in output}) != len(output):
            raise ValueError("Duplicate input keys in microbatch")
        if args.architecture != "B0" or batch_id % 1000 == 0:
            print(json.dumps({"received": len(raw), "batch": batch_id}), flush=True)
        timestamp = sink.write(output, batch_id)
        for row in output:
            committed.setdefault(row["article_key"], (timestamp, row["sent_at"]))
        if not first_batch:
            first_batch.extend(output)
        batches.append(batch_id)
        log.write(json.dumps({"batch": batch_id, "committed_at": timestamp,
                              "keys": [r["article_key"] for r in output]}) + "\n")
        if args.architecture != "B0" or batch_id % 1000 == 0 or len(committed) == number:
            print(json.dumps({"committed": len(committed), "batch": batch_id}), flush=True)
    try:
        if args.architecture in ("A4", "A5"):
            spark = spark_session()
        sink = DeltaSink(spark, storage, args.run_id) if args.architecture == "A5" else SqlSink(args.architecture, storage)
        if spark:
            from pyspark.sql import functions as F
            from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType
            schema = StructType([StructField(k, DoubleType() if k == "sent_at" else LongType() if k in ("fatalities", "injuries") else StringType(), True)
                                 for k in list(rows[0]) + ["run_id", "sent_at"]])
            source = (spark.readStream.format("kafka").option("kafka.bootstrap.servers", "kafka:9092")
                      .option("subscribe", topic).option("startingOffsets", "earliest")
                      .option("maxOffsetsPerTrigger", 512).load())
            parsed = source.select(F.from_json(F.col("value").cast("string"), schema).alias("data")).select("data.*")
            def foreach_batch(frame, batch_id):
                commit([r.asDict() for r in frame.toLocalIterator()], batch_id)
            query = (parsed.writeStream.foreachBatch(foreach_batch)
                     .option("checkpointLocation", str(storage / "checkpoint"))
                     .trigger(processingTime="1 second").start())
        elif args.architecture == "B0":
            from redis_baseline import RedisConsumer
            consumer = RedisConsumer(topic)
        else:
            consumer = KafkaConsumer(topic, bootstrap_servers="kafka:9092", group_id=args.run_id,
                                     auto_offset_reset="earliest", enable_auto_commit=False,
                                     max_poll_records=512,
                                     value_deserializer=lambda value: json.loads(value.decode("utf-8")))
        phase.write_text(json.dumps({"run_id": args.run_id, "active": True}), encoding="utf-8")
        producer = produce
        if args.architecture == "B0":
            from redis_baseline import produce_redis
            producer = produce_redis
        thread = threading.Thread(target=producer, args=(rows, topic, args.run_id, rate, state), daemon=True)
        thread.start()
        start = time.monotonic()
        while len(committed) < number:
            if state.get("error"):
                raise RuntimeError(state["error"])
            if time.monotonic() - start > args.timeout:
                raise TimeoutError(f"Only {len(committed)}/{number} committed")
            if query:
                if query.exception():
                    raise RuntimeError(str(query.exception()))
                time.sleep(0.1)
            elif args.architecture == "B0":
                row = consumer.take()
                if row is not None:
                    commit([row], len(batches))
                    consumer.ack()  # Same production queue; ACK strictly after commit.
            else:
                raw = []
                deadline = time.monotonic() + 1
                while len(raw) < 512 and time.monotonic() < deadline:
                    messages = consumer.poll(timeout_ms=max(1, int((deadline - time.monotonic()) * 1000)), max_records=512 - len(raw))
                    raw.extend(message.value for group in messages.values() for message in group)
                if raw:
                    commit(raw, len(batches))
                    consumer.commit()  # Never acknowledge Kafka before storage commit.
        thread.join(timeout=130)
        assert state.get("sent_count") == number and not state.get("error"), state
        if args.architecture == "B0":
            consumer.verify_empty()
        final_commit = max(value[0] for value in committed.values())
        log.flush()
        phase.write_text(json.dumps({"run_id": args.run_id, "active": False}), encoding="utf-8")
        if query:
            query.stop()
            query = None
        # Simulate the critical crash window: storage committed, Kafka/checkpoint
        # not acknowledged, so the identical first microbatch is delivered again.
        sink.write(first_batch, batches[0])
        export_s = sink.export() if args.architecture == "A5" else 0.0
        actual = sink.rows()
        expected = transform([dict(r, run_id=args.run_id, sent_at=0) for r in rows])
        keys = [r["article_key"] for r in actual]
        missing = len({r["article_key"] for r in rows} - set(keys))
        duplicate = len(keys) - len(set(keys))
        output_digest, expected_digest = digest(actual), digest(expected)
        checks = {"input_count": number, "output_count": len(keys), "missing_count": missing,
                  "duplicate_count": duplicate, "retry_pass": len(actual) == number and duplicate == 0,
                  "output_digest": output_digest, "expected_digest": expected_digest,
                  "content_equal": output_digest == expected_digest}
        (work / "correctness.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        assert not missing and not duplicate and len(actual) == number and checks["content_equal"], checks
        query_results, durations = {}, []
        for name, sql in QUERIES.items():
            sink.query(sql)  # Warm-up excluded, same SQL on all stores.
            timings = []
            for _ in range(15):
                tick = time.perf_counter()
                result = sink.query(sql)
                timings.append((time.perf_counter() - tick) * 1000)
            query_results[name] = {"p95_ms": percentile(timings, .95), "rows": result}
            durations.extend(timings)
        (work / "queries.json").write_text(json.dumps(query_results, ensure_ascii=False, indent=2), encoding="utf-8")
        latencies = [(commit_time - sent) * 1000 for commit_time, sent in committed.values()]
        assert min(latencies) >= 0
        elapsed = final_commit - state["first_sent_at"]
        metrics = {"architecture": args.architecture, "workload": args.workload, "run_id": args.run_id,
                   "input_count": number, "output_count": len(actual), "total_duration_s": elapsed,
                   "throughput_articles_s": len(actual) / elapsed,
                   "latency_p50_ms": percentile(latencies, .5), "latency_p95_ms": percentile(latencies, .95),
                   "failed_count": 0, "missing_count": missing, "duplicate_count": duplicate,
                   "query_p95_ms": percentile(durations, .95), "snapshot_export_s": export_s,
                   "drain_s": max(0, final_commit - state["last_sent_at"]), "retry_pass": True,
                   "output_digest": output_digest, "batch_count": len(batches)}
        (work / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(json.dumps(metrics), flush=True)
    finally:
        phase.write_text(json.dumps({"run_id": args.run_id, "active": False}), encoding="utf-8")
        if query:
            query.stop()
        if consumer:
            consumer.close()
        if sink:
            sink.close()
        if spark:
            spark.stop()
        log.close()
        if admin:
            admin.close()


if __name__ == "__main__":
    main()
