"""Configuration parsing and the cross-field invariants enforced at startup."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    AppEnv,
    AuctionMechanism,
    LLMProvider,
    Settings,
    get_settings,
)

pytestmark = pytest.mark.unit


def test_defaults_are_sane(monkeypatch: pytest.MonkeyPatch) -> None:
    """Declared defaults apply when nothing is set in the environment."""
    for var in (
        "MARKET_TICK_MINUTES",
        "AUCTION_MECHANISM",
        "FEED_IN_TARIFF",
        "RETAIL_TARIFF",
        "LLM_PROVIDER",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings()

    assert settings.market_tick_minutes == 15
    assert settings.auction_mechanism is AuctionMechanism.UNIFORM
    assert settings.llm_provider is LLMProvider.STUB
    assert settings.feed_in_tariff < settings.retail_tariff


def test_cors_origins_are_split_and_stripped(settings: Settings) -> None:
    # The fixture supplies padding and a trailing empty entry.
    assert settings.cors_origin_list == [
        "http://localhost:5173",
        "http://localhost:3000",
    ]


def test_is_production_reflects_environment() -> None:
    assert Settings(app_env=AppEnv.DEVELOPMENT).is_production is False
    assert (
        Settings(
            app_env=AppEnv.PRODUCTION, debug=False, jwt_secret_key="a-real-production-secret"
        ).is_production
        is True
    )


def test_inverted_tariff_band_is_rejected() -> None:
    """A seller's floor above a buyer's ceiling makes objective O6 unreachable."""
    with pytest.raises(ValidationError, match="strictly less than"):
        Settings(feed_in_tariff=8.0, retail_tariff=3.0)


def test_collapsed_tariff_band_is_rejected() -> None:
    """Equal tariffs leave no spread, so no trade can benefit both parties."""
    with pytest.raises(ValidationError, match="strictly less than"):
        Settings(feed_in_tariff=5.0, retail_tariff=5.0)


def test_inverted_voltage_band_is_rejected() -> None:
    with pytest.raises(ValidationError, match="voltage_min_pu"):
        Settings(voltage_min_pu=1.05, voltage_max_pu=0.95)


def test_production_requires_a_groq_key() -> None:
    with pytest.raises(ValidationError, match="GROQ_API_KEY"):
        Settings(
            app_env=AppEnv.PRODUCTION,
            debug=False,
            llm_provider=LLMProvider.GROQ,
            groq_api_key="",
        )


def test_production_accepts_groq_with_a_key() -> None:
    settings = Settings(
        app_env=AppEnv.PRODUCTION,
        debug=False,
        llm_provider=LLMProvider.GROQ,
        groq_api_key="gsk_test_key",
        jwt_secret_key="a-real-production-secret",
    )
    assert settings.is_production is True


def test_production_rejects_debug() -> None:
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        Settings(
            app_env=AppEnv.PRODUCTION,
            debug=True,
            llm_provider=LLMProvider.STUB,
            jwt_secret_key="a-real-production-secret",
        )


def test_stub_provider_needs_no_credentials_in_production() -> None:
    """CI runs in production-like config without any API key available."""
    settings = Settings(
        app_env=AppEnv.PRODUCTION,
        debug=False,
        llm_provider=LLMProvider.STUB,
        jwt_secret_key="a-real-production-secret",
    )
    assert settings.llm_provider is LLMProvider.STUB


def test_production_rejects_default_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dev-only JWT secret must never reach a real deployment.

    Must not depend on the ambient environment being free of JWT_SECRET_KEY —
    CI sets one at the job level (for the integration tests that need a real
    database session), which would otherwise silently override the class
    default and make this test pass for the wrong reason: not because the
    validator caught the dev secret, but because a real one was already there.
    """
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(app_env=AppEnv.PRODUCTION, debug=False, llm_provider=LLMProvider.STUB)


def test_production_accepts_a_real_jwt_secret() -> None:
    settings = Settings(
        app_env=AppEnv.PRODUCTION,
        debug=False,
        llm_provider=LLMProvider.STUB,
        jwt_secret_key="a-real-production-secret",
    )
    assert settings.jwt_secret_key == "a-real-production-secret"


def test_port_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        Settings(api_port=70000)


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
