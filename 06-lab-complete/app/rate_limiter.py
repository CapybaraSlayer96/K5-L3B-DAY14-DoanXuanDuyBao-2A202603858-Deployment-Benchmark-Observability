"""Sliding window rate limit trên Redis sorted set, chia sẻ giữa worker/instance."""
import hashlib
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Vượt RATE_LIMIT_PER_MINUTE trong 60s -> 429 + Retry-After. Redis lỗi -> 503."""
    now = time.time()
    redis_key = "ratelimit:" + hashlib.sha256(key.encode()).hexdigest()[:16]
    member = f"{now}:{uuid.uuid4().hex}"
    try:
        pipe = r.pipeline(transaction=True)
        pipe.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
        pipe.zadd(redis_key, {member: now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        _, _, count, _ = pipe.execute()
        if count > settings.rate_limit_per_minute:
            r.zrem(redis_key, member)
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = int(oldest[0][1] + WINDOW_SECONDS - now) + 1 if oldest else WINDOW_SECONDS
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(max(retry_after, 1))},
            )
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable")
