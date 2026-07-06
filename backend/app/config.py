"""Env-driven settings (spec §17). Model names and RAG thresholds live here, never in code."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- OpenAI ---
    OPENAI_API_KEY: str = ""  # empty is fine until Phase 2 (no OpenAI calls in Phase 1)
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    CHAT_MODEL: str = "gpt-4o-mini"
    VISION_MODEL: str = "gpt-4o-mini"

    # --- Database ---
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/tractor"

    # --- Auth ---
    JWT_SECRET: str = "change-me"
    JWT_EXPIRY_MINUTES: int = 120
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "change-me"

    # --- RAG tuning ---
    RETRIEVAL_TOP_K: int = 8
    IMAGE_SIMILARITY_THRESHOLD: float = 0.35
    CHUNK_TARGET_TOKENS: int = 650
    CHUNK_OVERLAP_TOKENS: int = 80

    # --- Limits / abuse protection ---
    MAX_QUESTION_CHARS: int = 1000
    MAX_HISTORY_MESSAGES: int = 6  # client-sent turns used for follow-up understanding
    MAX_HISTORY_CHARS: int = 4000  # per-message content cap (bounds condensation tokens)
    CHAT_RATE_LIMIT: str = "20/minute"
    LOGIN_RATE_LIMIT: str = "10/minute"
    MAX_UPLOAD_MB: int = 50

    # --- Storage / server ---
    STORAGE_PATH: str = "/data/storage"
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
