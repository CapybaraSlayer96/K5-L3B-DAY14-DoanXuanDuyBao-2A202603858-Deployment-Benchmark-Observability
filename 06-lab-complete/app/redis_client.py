"""Redis client dùng chung. Kết nối lazy, app khởi động được khi Redis chưa sẵn sàng."""
import logging

import redis

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)


def redis_healthy() -> bool:
    """Ping Redis. Lỗi kết nối -> False."""
    try:
        return bool(r.ping())
    except Exception as exc:
        logging.getLogger("agent").warning(
            "redis_unhealthy", extra={"fields": {"event": "redis_unhealthy", "error": type(exc).__name__}}
        )
        return False
