import argparse
from contextlib import contextmanager
import logging
import os
from pathlib import Path
import signal
import threading

from redis.exceptions import RedisError

from .message import parse_message
from .pipeline import ArticleProcessor
from .queue import ArticleQueue
from .repository import ProvisionalRepository
from config.streaming import database_path, queue_name, redis_client

LOG = logging.getLogger(__name__)


@contextmanager
def writer_lock(database):
    """OS releases the lock after crashes; also guards same-host recovery."""
    path = Path(str(database) + ".writer.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Consumer:
    def __init__(self, queue, processor, stop=None, retry_seconds=2):
        self.queue, self.processor = queue, processor
        self.stop = stop if stop is not None else threading.Event()
        self.retry_seconds = retry_seconds

    def once(self):
        raw = self.queue.take()
        if raw is None:
            return None
        try:
            row = parse_message(raw)
        except ValueError as error:
            LOG.warning("malformed message: %s", error)
            self.queue.fail(raw, error, permanent=True)
            return {"status": "invalid"}
        try:
            result = self.processor.process(row)
        except Exception as error:
            LOG.exception("processing failed article_key=%s", row["article_key"])
            self.queue.fail(raw, error, permanent=isinstance(error, ValueError))
            self.stop.wait(self.retry_seconds)
            return {"status": "failed"}
        self.queue.ack(raw)
        LOG.info("processed article_key=%s result=%s", row["article_key"], result)
        return result

    def run(self):
        recover = True
        while not self.stop.is_set():
            try:
                if recover:
                    self.queue.recover()
                    recover = False
                self.once()
            except RedisError:
                LOG.exception("Redis unavailable; reconnecting, in-flight messages retained")
                recover = True
                self.stop.wait(self.retry_seconds)


def main():
    parser = argparse.ArgumentParser(description="Run one provisional event writer per queue/database")
    parser.add_argument("--database", type=Path, default=database_path())
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    client = redis_client()
    try:
        with writer_lock(args.database):
            repo = ProvisionalRepository(args.database)
            try:
                repo.initialize()
                Consumer(ArticleQueue(client, queue_name()), ArticleProcessor(repo), stop).run()
            finally:
                repo.close()
    finally:
        client.close()


if __name__ == "__main__":
    main()
