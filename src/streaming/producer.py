import argparse
import json
import logging
from pathlib import Path

from redis.exceptions import RedisError
from .message import normalize_article
from config.streaming import redis_client, queue_name

LOG = logging.getLogger(__name__)


def enqueue_article(article, client=None, queue=None):
    """Crawler interface: pass its Bronze row plus source; failures propagate."""
    owned = client is None
    try:
        row = normalize_article(article)
        if owned:
            client = redis_client()
        client.lpush(
            queue or queue_name(), json.dumps(row, ensure_ascii=False, allow_nan=False))
        LOG.info("enqueued article_key=%s", row["article_key"])
        return row["article_key"]
    except (ValueError, TypeError, RedisError):
        LOG.exception("enqueue failed; caller must retain Bronze and retry")
        raise
    finally:
        if owned and client is not None:
            client.close()


def main():
    parser = argparse.ArgumentParser(description="Enqueue one RSS Bronze JSON object")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        enqueue_article(json.loads(args.file.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, TypeError, RedisError):
        LOG.exception("producer command failed")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
