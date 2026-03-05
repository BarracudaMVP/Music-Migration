"""
Shared pytest configuration.

Sets environment variables BEFORE any project modules are imported so that
core/db/session.py creates an in-memory SQLite engine for tests (no file, no
connection to a real DB).  Workers and Redis are not needed for unit tests.
"""
import os

# Override DB before any project imports create the engine
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
