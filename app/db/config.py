from functools import lru_cache
import os


class Settings:
    def __init__(self) -> None:
        # Use asyncpg driver for SQLAlchemy async support.
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/reportai",
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
