"""Redis client dùng chung. Kết nối lazy, app khởi động được khi Redis chưa sẵn sàng hoặc URL sai."""
import logging

import redis

from app.config import settings

logger = logging.getLogger("agent")

_UNREACHABLE_URL = "redis://redis.invalid:6379/0"


def _make_client() -> redis.Redis:
    kwargs = dict(decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    try:
        return redis.from_url(settings.redis_url, **kwargs)
    except ValueError:
        # URL sai scheme: không được làm sập process, /health vẫn phải 200 và /ready trả 503
        logger.error("redis_url_invalid", extra={"fields": {"event": "redis_url_invalid",
                                                              "hint": "REDIS_URL must start with redis://"}})
        return redis.from_url(_UNREACHABLE_URL, **kwargs)


r = _make_client()


def redis_healthy() -> bool:
    """Ping Redis. Lỗi kết nối -> False."""
    try:
        return bool(r.ping())
    except Exception as exc:
        logger.warning("redis_unhealthy", extra={"fields": {"event": "redis_unhealthy",
                                                              "error": type(exc).__name__}})
        return False
