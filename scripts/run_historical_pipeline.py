"""Default CLI uses A2 Bronze/Kafka; retain legacy Redis helper for compatibility."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

from config import DATA_ARTIFACTS_DIR
from preprocessors.run import run_preprocessors
from filters import run_filters
from extractors import run_extractors
from events import run_events
from streaming.replay import replay
from dashboard.publish import publish
from batch.run import DEFAULT_DATABASE
from events.locking import writer_lock


def main():
    stages = [("preprocess", run_preprocessors), ("filter", run_filters),
              ("extract", run_extractors), ("events", run_events),
              ("streaming", replay), ("publish", publish)]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-at", choices=[name for name, _ in stages], default="preprocess")
    args = parser.parse_args()
    progress = Path(DATA_ARTIFACTS_DIR) / "historical_pipeline_progress.json"
    progress.parent.mkdir(parents=True, exist_ok=True)
    status = {"started_at": datetime.now(timezone.utc).isoformat(), "stages": {}}
    def save():
        temporary = progress.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(status, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        temporary.replace(progress)
    active = False
    for name, function in stages:
        active = active or name == args.start_at
        if not active:
            continue
        status["current_stage"] = name
        status["status"] = "running"
        save()
        print(f"[Historical pipeline] START {name}", flush=True)
        try:
            result = function()
            if name == "publish":
                # Keep the normal Gold Batch path in sync with the published snapshot.
                canonical = Path(DATA_ARTIFACTS_DIR) / result["path"] / "gold" / "batch" / "canonical.duckdb"
                with writer_lock(DEFAULT_DATABASE):
                    DEFAULT_DATABASE.parent.mkdir(parents=True, exist_ok=True)
                    temporary = DEFAULT_DATABASE.with_suffix(".history-stage.duckdb")
                    shutil.copy2(canonical, temporary)
                    temporary.replace(DEFAULT_DATABASE)
            status["stages"][name] = {"status": "complete", "finished_at": datetime.now(timezone.utc).isoformat(),
                                     "result": result}
            save()
            print(f"[Historical pipeline] DONE {name}", flush=True)
        except Exception as error:
            status.update(status="failed", error=str(error))
            save()
            raise
    status.update(status="complete", finished_at=datetime.now(timezone.utc).isoformat())
    save()
    print(json.dumps(status, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    # Historical CLI now follows the same Bronze -> Kafka path as the live service.
    from a2.runtime import main as a2_main
    a2_main()
