"""Environment configuration and Redis client factory for tasks 4.1–4.2."""

import os
from pathlib import Path

from .main import DATA_GOLD_DIR  # also loads .env
import redis
from redis.backoff import NoBackoff
from redis.retry import Retry


def database_path():
    return Path(os.getenv("STREAM_DATABASE_PATH", str(Path(DATA_GOLD_DIR) / "streaming" / "provisional.duckdb")))


def queue_name():
    return os.getenv("REDIS_ARTICLE_QUEUE", "article_queue")


def redis_client():
    return redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
        socket_connect_timeout=3, socket_timeout=10,
        retry=Retry(NoBackoff(), 0),
    )
