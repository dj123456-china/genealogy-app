import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'))


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./family_tree.db",
    )
    secret_key: str = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
    cors_origins: list[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cors_origins",
            _csv(os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174")),
        )


settings = Settings()
