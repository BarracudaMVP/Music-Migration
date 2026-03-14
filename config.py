from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


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
    sc_playlist_batch_size: int = Field(default=500)   # макс. треков в одном SC-плейлисте при playlist_mode
    match_threshold: float = Field(default=75.0)
    match_uncertain_floor: float = Field(default=60.0)
    search_limit: int = Field(default=5)               # кандидатов на трек при поиске на целевой платформе
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="pretty")  # "pretty" = colored stderr (dev), "json" = JSON stdout (Docker)

    # FastAPI (MVP4)
    database_url: str = Field(default="")
    api_base_url: str = Field(default="http://localhost:8000")   # internal bot→API (http://api:8000 in Docker)
    web_base_url: str = Field(default="")                        # public URL shown to users; falls back to api_base_url
    api_internal_token: str = Field(default="")

    @property
    def public_url(self) -> str:
        """Public-facing URL for links shown to users (web UI, OAuth callbacks)."""
        return (self.web_base_url or self.api_base_url).rstrip("/")

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

    # Yandex OAuth callback (oauth.yandex.ru app)
    # If set — uses redirect flow (button, no code copy-paste). Must be registered in the app.
    # Example: https://musicmigration.site/auth/yandex/callback
    yandex_redirect_uri: str = Field(default="")

    # SoundCloud OAuth (soundcloud.com/you/apps)
    sc_client_id: str = Field(default="")
    sc_client_secret: str = Field(default="")
    sc_redirect_uri: str = Field(default="http://localhost:8000/auth/soundcloud/callback")

    # SPA / CORS (MM-81)
    cors_origins: str = Field(default="http://localhost:3000")  # comma-separated
    jwt_secret_key: str = Field(default="change-me-jwt-secret")
    jwt_access_token_ttl: int = Field(default=900)        # seconds (15 min)
    jwt_refresh_token_ttl: int = Field(default=2592000)   # seconds (30 days)

    # Dev mode (local development only — NEVER enable in production)
    dev_mode: bool = Field(default=False)

    @model_validator(mode="after")
    def guard_dev_mode(self) -> "Settings":
        """Force dev_mode=False if a non-localhost public URL is configured.

        Prevents DEV_MODE from being accidentally active in production even
        if someone copies .env.dev to the server.
        """
        if not self.dev_mode:
            return self
        public_url = self.web_base_url or self.api_base_url
        _local = ("localhost", "127.0.0.1", "0.0.0.0")
        if public_url and not any(h in public_url for h in _local):
            self.dev_mode = False
        return self

    def get_allowed_users(self) -> set[int]:
        if not self.allowed_users.strip():
            return set()
        return {int(uid.strip()) for uid in self.allowed_users.split(",") if uid.strip()}


settings = Settings()
