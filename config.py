from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = ""

    # Яндекс OAuth (oauth.yandex.ru)
    yandex_client_id: str = ""
    yandex_client_secret: str = ""

    # Whitelist Telegram user ID через запятую: "123456789,987654321"
    # Если пусто — бот открыт для всех (не рекомендуется для личного бота)
    allowed_users: str = ""

    # Ключ шифрования токенов в БД (Fernet, base64).
    # Сгенерировать: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Если пусто — токены хранятся plain text (небезопасно!)
    db_encryption_key: str = ""

    # CLI токены
    yandex_token: str = ""
    soundcloud_token: str = ""

    # Миграция
    sc_rate_limit_sleep: float = Field(default=2.0)
    sc_playlist_batch_size: int = Field(default=500)   # макс. треков в одном SC-плейлисте при playlist_mode
    match_threshold: float = Field(default=75.0)
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="pretty")  # "pretty" = colored stderr (dev), "json" = JSON stdout (Docker)

    # FastAPI (MVP4)
    database_url: str = Field(default="")
    api_base_url: str = Field(default="http://localhost:8000")
    api_internal_token: str = Field(default="")

    # ARQ Worker (MVP5)
    redis_url: str = Field(default="redis://localhost:6379")

    # Web UI (MVP7) — used for signing session cookies
    secret_key: str = Field(default="change-me-in-production")

    # Admin UI (MVP8)
    admin_password: str = Field(default="admin")

    # Web UI access control (MM-31)
    web_enabled: bool = Field(default=True)          # false = disable web UI and admin (API/bot still work)
    web_allowed_ips: str = Field(default="")         # comma-separated IPs; empty = allow all

    # Proxy для Яндекс Музыки (RU IP)
    ym_proxy_url: str = Field(default="")

    # Spotify OAuth (developer.spotify.com)
    spotify_client_id: str = Field(default="")
    spotify_client_secret: str = Field(default="")
    spotify_redirect_uri: str = Field(default="http://localhost:8000/auth/spotify/callback")

    # SoundCloud OAuth (soundcloud.com/you/apps)
    sc_client_id: str = Field(default="")
    sc_client_secret: str = Field(default="")
    sc_redirect_uri: str = Field(default="http://localhost:8000/auth/soundcloud/callback")

    def get_allowed_users(self) -> set[int]:
        if not self.allowed_users.strip():
            return set()
        return {int(uid.strip()) for uid in self.allowed_users.split(",") if uid.strip()}


settings = Settings()
