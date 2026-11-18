"""Replay retained real Kafka messages; assert journal and event DBs unchanged."""
import hashlib
import json
from pathlib import Path

from a2.config import current, HOME, atomic_json
from a2.runtime import Runtime
from events.locking import writer_lock


def main():
    with writer_lock(HOME / "runtime"):
        settings = current()
        runtime = Runtime(settings)
        try:
            # Complete any pending version migration before taking a baseline.
            runtime.outbox()
            runtime.drain(True)
            before = {"counts": runtime.state.counts(), "revision": runtime.state.meta("revision"),
                      "stream_sha256": hashlib.sha256(Path(settings["stream"]).read_bytes()).hexdigest(),
                      "batch_sha256": hashlib.sha256(Path(settings["canonical"]).read_bytes()).hexdigest()}
            runtime.consumer.seek(runtime.tp, 0)
            replay = runtime.drain(True)
            after = {"counts": runtime.state.counts(), "revision": runtime.state.meta("revision"),
                     "stream_sha256": hashlib.sha256(Path(settings["stream"]).read_bytes()).hexdigest(),
                     "batch_sha256": hashlib.sha256(Path(settings["canonical"]).read_bytes()).hexdigest()}
            assert before == after, (before, after)
            assert replay["consumed"]["replayed"] == before["counts"]["messages"]
            assert replay["consumed"]["inserted"] == replay["consumed"]["updated"] == 0
            assert replay["kafka_target"] == replay["kafka_committed"]
            assert runtime.state.db.execute("SELECT count(*) FROM kafka_messages WHERE message_fingerprint IS NULL").fetchone()[0] == 0
            result = {"verified": True, "before": before, "after": after, "replay": replay}
            atomic_json(HOME / "replay_verification.json", result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        finally:
            runtime.close()


if __name__ == "__main__":
    main()
