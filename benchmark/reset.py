"""Clean ONE explicitly named benchmark run; production stores are inaccessible."""
import argparse
import json
from pathlib import Path
import re
import shutil
from kafka.admin import KafkaAdminClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    args = parser.parse_args()
    if not re.fullmatch(r"(?:b0|a2|a4|a5|smoke)-[a-z0-9-]+", args.run_id):
        raise ValueError("Expected an explicit benchmark run ID")
    base = Path(__file__).resolve().parent
    phase = base / "work/phase.json"
    if phase.exists() and json.loads(phase.read_text()).get("active"):
        raise RuntimeError("A benchmark is active; refuse reset")
    target = (base / "work" / args.run_id).resolve()
    if not target.is_relative_to((base / "work").resolve()) or target == (base / "work").resolve():
        raise ValueError("Invalid cleanup path")
    topic = "bench-" + args.run_id
    if args.run_id.startswith("b0-"):
        from redis_baseline import client
        connection = client()
        try:
            connection.delete(topic, topic + ":processing", topic + ":dead", topic + ":attempts")
        finally:
            connection.close()
    else:
        admin = KafkaAdminClient(bootstrap_servers="kafka:9092")
        try:
            if topic in admin.list_topics():
                admin.delete_topics([topic])
        finally:
            admin.close()
    if target.exists():
        shutil.rmtree(target)
    storage = (Path("/storage") / args.run_id).resolve()
    if storage.is_relative_to(Path("/storage").resolve()) and storage != Path("/storage").resolve() and storage.exists():
        shutil.rmtree(storage)
    print("Removed benchmark topic and isolated output/checkpoint:", args.run_id)
    print("PostgreSQL output is transactionally recreated by each new serial A4 run. Results/logs retained.")


if __name__ == "__main__":
    main()
