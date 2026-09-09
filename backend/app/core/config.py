"""Typed application configuration, resolved once from the environment.

Every tunable in the system is declared here so that a reader can see the whole
operating surface in one file, and so that an invalid deployment fails loudly at
startup rather than silently misbehaving during a market tick.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogFormat(StrEnum):
    """Log rendering style: human-readable locally, structured in production."""

    CONSOLE = "console"
    JSON = "json"


class LLMProvider(StrEnum):
    """Backend serving natural-language explanations.

    The LLM never sits in the trading critical path, so any of these may be
    swapped at runtime without affecting market outcomes or settlement.
    """

    GROQ = "groq"
    OLLAMA = "ollama"
    STUB = "stub"


class AuctionMechanism(StrEnum):
    """Rule used to price a cleared double auction."""

    UNIFORM = "uniform"
    PAY_AS_BID = "pay_as_bid"
    MID_MARKET_RATE = "mid_market_rate"


class Settings(BaseSettings):
    """Runtime configuration.

    Field names map case-insensitively to environment variables, so ``app_env``
    is populated from ``APP_ENV``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application --------------------------------------------------------
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_name: str = "energy-transfer"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.CONSOLE

    # --- API ----------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_v1_prefix: str = "/api/v1"

    # Stored as a raw string because pydantic-settings would otherwise try to
    # JSON-decode a list-typed field, which makes the .env syntax awkward.
    # Use the `cors_origin_list` property to read it.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Market rules -------------------------------------------------------
    market_tick_minutes: int = Field(default=15, ge=1, le=60)
    feed_in_tariff: float = Field(default=3.00, ge=0)
    retail_tariff: float = Field(default=8.00, ge=0)
    currency: str = "INR"
    auction_mechanism: AuctionMechanism = AuctionMechanism.UNIFORM

    # --- Grid safety --------------------------------------------------------
    grid_feeder: str = "ieee33"
    transformer_capacity_kw: float = Field(default=250.0, gt=0)
    voltage_min_pu: float = Field(default=0.95, gt=0, lt=2)
    voltage_max_pu: float = Field(default=1.05, gt=0, lt=2)

    # --- LLM ----------------------------------------------------------------
    llm_provider: LLMProvider = LLMProvider.STUB
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2:3b"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_cache_ttl_seconds: int = Field(default=3600, ge=0)

    # --- Simulator ----------------------------------------------------------
    sim_households: int = Field(default=5, ge=1, le=1000)
    sim_prosumer_ratio: float = Field(default=0.6, ge=0, le=1)
    sim_seed: int = 42

    # --- Derived ------------------------------------------------------------

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list, from the comma-separated env value."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """True when running in the production environment."""
        return self.app_env is AppEnv.PRODUCTION

    # --- Cross-field invariants ---------------------------------------------

    @model_validator(mode="after")
    def _validate_tariff_spread(self) -> Self:
        """Reject a tariff band that makes mutually beneficial trade impossible.

        The market clears strictly inside ``[feed_in_tariff, retail_tariff]``.
        If the band inverts or collapses, no price can leave both the seller
        better off than exporting and the buyer better off than importing, and
        objective O6 becomes unreachable. Fail at startup instead.
        """
        if self.feed_in_tariff >= self.retail_tariff:
            msg = (
                f"feed_in_tariff ({self.feed_in_tariff}) must be strictly less than "
                f"retail_tariff ({self.retail_tariff}); otherwise no P2P price can "
                f"benefit both parties."
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_voltage_band(self) -> Self:
        """Reject an inverted statutory voltage band."""
        if self.voltage_min_pu >= self.voltage_max_pu:
            msg = (
                f"voltage_min_pu ({self.voltage_min_pu}) must be strictly less than "
                f"voltage_max_pu ({self.voltage_max_pu})."
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> Self:
        """Refuse to start in production with a provider that has no credentials."""
        if self.app_env is AppEnv.PRODUCTION:
            if self.llm_provider is LLMProvider.GROQ and not self.groq_api_key:
                msg = "GROQ_API_KEY is required when LLM_PROVIDER=groq in production."
                raise ValueError(msg)
            if self.debug:
                msg = "DEBUG must be false in production."
                raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that configuration is parsed and validated exactly once. Tests
    that need to vary the environment should call ``get_settings.cache_clear()``.
    """
    return Settings()
