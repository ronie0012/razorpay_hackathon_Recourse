import os
from functools import lru_cache

from pydantic import BaseModel
from dotenv import load_dotenv


load_dotenv()


class Settings(BaseModel):
    database_url: str = "sqlite:///./recourse.db"
    fixture_webhook_secret: str = "local-fixture-secret"
    command_signing_secret: str = "local-command-secret"
    demo_mode: bool = True
    test_mode: bool = True
    cors_origins: str = "http://localhost:5173"
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    razorpay_base_url: str = "https://api.razorpay.com/v1"
    razorpay_timeout_seconds: float = 8.0
    razorpay_enabled: bool = False
    openrouter_api_key: str | None = None
    openrouter_model: str = "liquid/lfm-2.5-2.6b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 30.0
    openrouter_max_tokens: int = 2000
    openrouter_app_url: str | None = None
    openrouter_app_title: str = "RECOURSE"
    openrouter_enabled: bool = True

@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./recourse.db"),
        fixture_webhook_secret=os.getenv("FIXTURE_WEBHOOK_SECRET", "local-fixture-secret"),
        command_signing_secret=os.getenv("COMMAND_SIGNING_SECRET", "local-command-secret"),
        demo_mode=os.getenv("DEMO_MODE", "true").lower() == "true",
        test_mode=os.getenv("TEST_MODE", "true").lower() == "true",
        cors_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173"),
        razorpay_key_id=os.getenv("RAZORPAY_KEY_ID"),
        razorpay_key_secret=os.getenv("RAZORPAY_KEY_SECRET"),
        razorpay_webhook_secret=os.getenv("RAZORPAY_WEBHOOK_SECRET"),
        razorpay_base_url=os.getenv("RAZORPAY_BASE_URL", "https://api.razorpay.com/v1"),
        razorpay_timeout_seconds=float(os.getenv("RAZORPAY_TIMEOUT_SECONDS", "8")),
        razorpay_enabled=os.getenv("RAZORPAY_ENABLED", "false").lower() == "true",
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "liquid/lfm-2.5-2.6b:free"),
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        openrouter_timeout_seconds=float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30")),
        openrouter_max_tokens=int(os.getenv("OPENROUTER_MAX_TOKENS", "2000")),
        openrouter_app_url=os.getenv("OPENROUTER_APP_URL"),
        openrouter_app_title=os.getenv("OPENROUTER_APP_TITLE", "RECOURSE"),
        openrouter_enabled=os.getenv("OPENROUTER_ENABLED", "true").lower() == "true",
    )
