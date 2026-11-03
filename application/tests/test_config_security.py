"""Security-related configuration tests (local-only LLM, admins, runtime overrides)."""

import pytest
from pydantic import ValidationError

from src.application.config import (
    ApiSecuritySettings,
    AppConfig,
    ConfigllmSettings,
    is_local_host,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:4000",
        "http://localhost",
        "http://litellm",  # Docker service name
        "http://oncoflow-api:8000",
        "http://10.0.0.12",
        "http://192.168.1.20:11434",
        "http://172.17.0.2",
        "http://[::1]:8080",
        "http://gpu-server.lan",
        "http://ollama.internal",
        "llama-cpp:8080",
    ],
)
def test_local_hosts_are_accepted(url):
    assert is_local_host(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://qwen3-8b-abc123.europe-west1.run.app",
        "http://8.8.8.8",
        "",
    ],
)
def test_remote_hosts_are_rejected(url):
    assert not is_local_host(url)


def test_remote_llm_refused_by_default():
    with pytest.raises(ValidationError, match="APP_ALLOW_REMOTE_LLM"):
        AppConfig(llm=ConfigllmSettings(url="https://api.openai.com"))


def test_remote_llm_allowed_with_explicit_opt_out():
    conf = AppConfig(
        llm=ConfigllmSettings(url="https://api.openai.com"), allow_remote_llm=True
    )
    assert conf.allow_remote_llm


def test_is_admin_open_when_not_configured():
    assert AppConfig(admin_users="").is_admin("anyone")


def test_is_admin_restricted_list_is_case_insensitive():
    conf = AppConfig(admin_users="alice, Bob@Hospital.fr")
    assert conf.is_admin("ALICE")
    assert conf.is_admin(None, "bob@hospital.fr")
    assert not conf.is_admin("mallory", "mallory@evil.test")
    assert not conf.is_admin(None)


def test_for_domain_keeps_security_settings():
    conf = AppConfig(
        admin_users="alice",
        allowed_domains="oncology,sma",
        api=ApiSecuritySettings(
            port=8088,
            cors_origins="https://oncologic.example.fr,https://sma.example.fr",
            rate_limit_enabled=True,
            rate_limit_requests=120,
        ),
    )
    other = conf.for_domain("sma")
    assert other.admin_users == "alice"
    assert other.allow_remote_llm == conf.allow_remote_llm
    assert other.api.port == 8088
    assert other.api.cors_origins_list == [
        "https://oncologic.example.fr",
        "https://sma.example.fr",
    ]
    assert other.api.rate_limit_enabled is True
    assert other.api.rate_limit_requests == 120


def test_cors_wildcard_with_credentials_rejected_in_prod():
    with pytest.raises(ValidationError, match="CORS wildcard"):
        AppConfig(
            dev_mode=False,
            api=ApiSecuritySettings(
                cors_enabled=True,
                cors_origins="*",
                cors_allow_credentials=True,
            ),
        )


def test_api_security_settings_lists_and_defaults():
    sec = ApiSecuritySettings(
        cors_origins=" http://localhost:3000 , https://app.example.fr ",
        cors_allow_methods="get, post, options",
        trusted_hosts="127.0.0.1, localhost, *.example.fr",
    )
    assert sec.cors_origins_list == ["http://localhost:3000", "https://app.example.fr"]
    assert sec.cors_methods_list == ["GET", "POST", "OPTIONS"]
    assert sec.trusted_hosts_list == ["127.0.0.1", "localhost", "*.example.fr"]
    assert sec.max_body_bytes == 52_428_800
    assert sec.security_headers_enabled is True
