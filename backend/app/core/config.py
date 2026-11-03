from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Morrow API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://morrow:morrow@localhost:5432/morrow"
    secret_key: str = "dev-only-change-this-secret-key-before-deploying"
    access_token_minutes: int = Field(default=30, ge=5, le=1440)
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    rate_limit_per_minute: int = Field(default=120, ge=1)
    auth_rate_limit_per_minute: int = Field(default=10, ge=1)
    expensive_rate_limit_per_minute: int = Field(default=10, ge=1)
    ml_artifact_dir: str = "var/models"
    redpanda_brokers: str = "localhost:19092"
    redpanda_events_topic: str = "business.events.v1"
    redpanda_dlq_topic: str = "business.events.dlq.v1"
    event_retry_limit: int = Field(default=8, ge=1, le=100)
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    voice_call_max_attempts: int = Field(default=3, ge=1, le=5)
    voice_test_mode: bool = True
    voice_live_calls_enabled: bool = False
    voice_public_base_url: str | None = None
    voice_transport: str = "gather"
    voice_provider: str = "twilio"
    # Optional Exotel Connect Voice AI configuration.  These values are kept
    # separate from Twilio and have no effect unless a future, explicitly
    # authorized Exotel call path is enabled.
    exotel_account_sid: str | None = None
    exotel_api_key: str | None = None
    exotel_api_token: str | None = None
    exotel_exophone: str | None = None
    exotel_region: str = "in"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    gemini_voice_timeout_seconds: float = Field(default=12, ge=1, le=60)

    @property
    def outbound_voice_configured(self) -> bool:
        return bool(
            not self.voice_test_mode
            and self.voice_live_calls_enabled
            and self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_from_number
        )

    @property
    def voice_delivery_enabled(self) -> bool:
        """Test mode delivers only simulated calls; live mode needs explicit opt-in."""
        return self.voice_test_mode or self.outbound_voice_configured

    @property
    def exotel_configured(self) -> bool:
        """Whether enough configuration exists for an explicit Exotel call.

        This intentionally remains false in test mode and is not used by the
        automatic alert worker.  A future live caller must also check consent,
        public HTTPS/WSS URLs, and an owner-triggered authorization.
        """
        return bool(
            not self.voice_test_mode
            and self.voice_live_calls_enabled
            and self.exotel_account_sid
            and self.exotel_api_key
            and self.exotel_api_token
            and self.exotel_exophone
        )

    @property
    def voice_webhooks_configured(self) -> bool:
        """Live calls require an externally reachable canonical HTTPS callback URL."""
        if not self.voice_public_base_url:
            return False
        parsed = urlsplit(self.voice_public_base_url)
        return parsed.scheme == "https" and bool(parsed.hostname)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
        return value

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        if self.app_env.lower() == "production":
            if self.secret_key.startswith("dev-only-"):
                raise ValueError("Set a unique SECRET_KEY before running in production")
            if self.secret_key == "replace-with-a-random-secret-at-least-32-characters-long":
                raise ValueError("Replace the example SECRET_KEY before running in production")
            origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
            if not origins:
                raise ValueError("Configure explicit HTTPS CORS_ORIGINS before production")
            if "*" in origins:
                raise ValueError("Wildcard CORS origins are not allowed in production")
            for origin in origins:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme != "https"
                    or not parsed.hostname
                    or parsed.path not in ("", "/")
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError("Production CORS_ORIGINS must be explicit HTTPS origins")
            if not self.database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
                raise ValueError("Production requires PostgreSQL")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
