import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from config import DATA_ARTIFACTS_DIR, DATA_SILVER_DIR, DATA_GOLD_DIR

HOME = Path(DATA_ARTIFACTS_DIR) / "a2"
CURRENT = HOME / "current.json"
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:29092")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def current(rebuild=False):
    if CURRENT.exists() and not rebuild:
        return json.loads(CURRENT.read_text(encoding="utf-8"))
    run = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8]
    value = dict(run_id=run, topic="news-articles-a2-" + run, group="news-a2-" + run,
                 state=str(Path(DATA_GOLD_DIR) / "a2" / run / "state.duckdb"),
                 silver=str(Path(DATA_SILVER_DIR) / "a2" / run),
                 stream=str(Path(DATA_GOLD_DIR) / "a2" / run / "provisional.duckdb"),
                 canonical=str(Path(DATA_GOLD_DIR) / "a2" / run / "canonical.duckdb"),
                 outbox=str(HOME / run / "bronze_outbox.json"))
    atomic_json(CURRENT, value)
    return value
