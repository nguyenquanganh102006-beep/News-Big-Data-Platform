"""Common Kafka producer. sent_at precedes send; delivery is verified."""
import json
import time
from kafka import KafkaProducer


def produce(rows, topic, run_id, rate, state):
    producer = None
    try:
        producer = KafkaProducer(bootstrap_servers="kafka:9092", acks="all", retries=5,
                                 max_in_flight_requests_per_connection=1,
                                 value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"))
        start = time.perf_counter()
        futures = []
        for index, original in enumerate(rows):
            if rate:
                delay = start + index / rate - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            row = dict(original, run_id=run_id, sent_at=time.time())
            state.setdefault("first_sent_at", row["sent_at"])
            state["last_sent_at"] = row["sent_at"]
            futures.append(producer.send(topic, key=row["article_key"].encode(), value=row))
        for future in futures:
            future.get(timeout=120)
        producer.flush(timeout=120)
        state["sent_count"] = len(rows)
    except BaseException as error:
        state["error"] = repr(error)
    finally:
        if producer:
            producer.close(timeout=10)
        state["done"] = True
