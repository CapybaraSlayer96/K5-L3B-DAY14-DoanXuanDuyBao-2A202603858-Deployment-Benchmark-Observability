"""Production AI agent: /health, /ready, /ask (auth + rate limit + cost guard), log JSON."""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "lvl": record.levelname,
            "msg": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc"] = record.exc_info[0].__name__
        return json.dumps(entry, ensure_ascii=False)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
logger = logging.getLogger("agent")
logger.handlers = [_handler]
logger.setLevel(logging.INFO)
logger.propagate = False


def log(event: str, **fields) -> None:
    logger.info(event, extra={"fields": {"event": event, **fields}})


@asynccontextmanager
async def lifespan(app: FastAPI):
    log("startup", environment=settings.environment, port=settings.port)
    yield
    log("shutdown")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log(
        "request",
        path=request.url.path,
        method=request.method,
        status=response.status_code,
        ms=round((time.perf_counter() - start) * 1000, 1),
    )
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.error("unhandled", extra={"fields": {"event": "error", "path": request.url.path,
                                                  "type": type(exc).__name__}})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not redis_healthy():
        return JSONResponse(status_code=503, content={"status": "not ready", "redis": "down"})
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()
    answer = llm_ask(body.question)
    cost = record_cost(len(body.question.split()) * 2, len(answer.split()) * 2)
    return {"question": body.question, "answer": answer, "cost_usd": round(cost, 8)}
