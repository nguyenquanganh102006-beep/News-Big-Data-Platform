"""Single-consumer reliable Redis List queue; ack only after DuckDB commit."""
import hashlib
import json


class ArticleQueue:
    def __init__(self, client, name):
        self.client, self.name = client, name
        self.processing = name + ":processing"
        self.dead = name + ":dead"
        self.attempts = name + ":attempts"

    def recover(self):
        # Consumer owns its database lock before touching the shared in-flight list.
        while self.client.rpoplpush(self.processing, self.name) is not None:
            pass

    def take(self, timeout=2):
        return self.client.brpoplpush(self.name, self.processing, timeout=timeout)

    def ack(self, raw):
        digest = hashlib.sha256(raw.encode()).hexdigest()
        self.client.eval("""
            redis.call('LREM', KEYS[1], 1, ARGV[1])
            redis.call('HDEL', KEYS[2], ARGV[2])
            return 1
        """, 2, self.processing, self.attempts, raw, digest)

    def fail(self, raw, error, permanent=False, max_attempts=3):
        digest = hashlib.sha256(raw.encode()).hexdigest()
        # Atomic transition: no gap between removing an item and retry/dead-letter.
        return self.client.eval("""
            local n = redis.call('HINCRBY', KEYS[3], ARGV[2], 1)
            if ARGV[3] == '1' or n >= tonumber(ARGV[4]) then
                redis.call('LPUSH', KEYS[4], ARGV[5])
                redis.call('HDEL', KEYS[3], ARGV[2])
            else
                redis.call('LPUSH', KEYS[2], ARGV[1])
            end
            redis.call('LREM', KEYS[1], 1, ARGV[1])
            return n
        """, 4, self.processing, self.name, self.attempts, self.dead,
            raw, digest, "1" if permanent else "0", max_attempts,
            json.dumps({"message": raw, "error": str(error)}, ensure_ascii=False))
