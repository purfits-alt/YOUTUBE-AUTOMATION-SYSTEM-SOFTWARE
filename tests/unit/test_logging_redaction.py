from __future__ import annotations

import json

import pytest
import structlog

from tubeforge.logging import REDACTED, configure_logging, redact_value

# Fake secrets shaped like the real formats (not real credentials).
FAKE_GOOGLE_KEY = "AIza" + "B" * 35
FAKE_ACCESS = "ya29.a0AfB_fakeTOKENvalue123"
FAKE_REFRESH = "1//0g" + "x" * 30
FAKE_GROQ = "gsk_" + "a1" * 15
FAKE_TELEGRAM = "123456789:" + "AbC_dEf-" * 5


@pytest.mark.parametrize(
    "secret",
    [FAKE_GOOGLE_KEY, FAKE_ACCESS, FAKE_REFRESH, FAKE_GROQ, FAKE_TELEGRAM, "Bearer abc.def.ghi"],
)
def test_secret_values_redacted_inside_strings(secret: str) -> None:
    out = redact_value(f"calling provider with {secret} now")
    assert secret not in out
    assert REDACTED in out


def test_dsn_password_redacted() -> None:
    out = redact_value("db=postgresql+psycopg://tubeforge:SuperSecret1@127.0.0.1:5432/tf")
    assert "SuperSecret1" not in out
    assert "tubeforge:***@127.0.0.1" in out


def test_sensitive_keys_redacted_recursively() -> None:
    out = redact_value(
        {"ok": 1, "nested": {"refresh_token": "abc", "api_key": "k", "list": [{"password": "p"}]}}
    )
    assert out == {
        "ok": 1,
        "nested": {"refresh_token": REDACTED, "api_key": REDACTED, "list": [{"password": REDACTED}]},
    }


def test_rendered_log_line_contains_no_secrets(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=True)
    log = structlog.get_logger("test")
    log.info(
        "oauth.refresh",
        authorization=f"Bearer {FAKE_ACCESS}",
        note=f"key {FAKE_GOOGLE_KEY}",
        code_verifier="v",
    )
    line = capsys.readouterr().out.strip().splitlines()[-1]
    data = json.loads(line)
    for secret in (FAKE_ACCESS, FAKE_GOOGLE_KEY):
        assert secret not in line
    assert data["authorization"] == REDACTED
    assert data["code_verifier"] == REDACTED
    assert data["event"] == "oauth.refresh"
