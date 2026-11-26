"""Cost guard: tổng chi phí LLM theo ngày lưu Redis, vượt DAILY_BUDGET_USD -> 402."""
import time

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
KEY_TTL_SECONDS = 2 * 24 * 3600


def _key() -> str:
    return "cost:" + time.strftime("%Y-%m-%d", time.gmtime())


def check_budget() -> None:
    """Gọi trước LLM. Hết budget -> 402. Redis lỗi -> 503."""
    try:
        spent = float(r.get(_key()) or 0.0)
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Cost guard unavailable")
    if spent >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi sau LLM. Cộng chi phí request vào tổng ngày, trả chi phí request."""
    cost = input_tokens / 1000 * PRICE_INPUT_PER_1K + output_tokens / 1000 * PRICE_OUTPUT_PER_1K
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(_key(), cost)
        pipe.expire(_key(), KEY_TTL_SECONDS)
        pipe.execute()
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Cost guard unavailable")
    return cost
