"""Config từ env var, đọc lúc import."""
import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    """Đọc env, bỏ khoảng trắng và dấu nháy thừa khi dán; rỗng -> default."""
    return os.getenv(name, "").strip().strip("\"'").strip() or default


@dataclass
class Settings:
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: _env("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL", "redis://localhost:6379/0"))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")))
    daily_budget_usd: float = field(default_factory=lambda: float(os.getenv("DAILY_BUDGET_USD", "1.0")))


settings = Settings()
