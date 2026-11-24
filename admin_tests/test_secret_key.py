"""SECRET_KEY rules for the main app's settings."""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
# api/settings.py reads the environment when it is imported, so give it a valid key first.
os.environ.setdefault("SECRET_KEY", "settings-test-key-that-is-long-enough-0123456789")

import pytest  # noqa: E402

from api import settings as settings_module  # noqa: E402


@pytest.fixture
def env(monkeypatch):
    for name in ("SECRET_KEY", "SOLOBIZ_DEBUG", "DATABASE_URL", "RENDER"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_hosted_app_refuses_to_start_without_a_secret_key(env):
    env.setenv("RENDER", "true")
    with pytest.raises(RuntimeError, match="Set the SECRET_KEY"):
        settings_module.load_settings()


def test_local_app_refuses_to_start_without_a_secret_key_unless_debug_is_requested(env):
    with pytest.raises(RuntimeError, match="SOLOBIZ_DEBUG"):
        settings_module.load_settings()


def test_debug_mode_generates_a_random_key_for_local_development_only(env):
    env.setenv("SOLOBIZ_DEBUG", "1")
    first = settings_module.load_settings().secret_key
    second = settings_module.load_settings().secret_key
    assert len(first) >= 32
    assert first != second
    assert first != "test-secret-key-not-for-production"


def test_debug_mode_does_not_apply_on_a_hosted_service(env):
    env.setenv("SOLOBIZ_DEBUG", "1")
    env.setenv("DATABASE_URL", "postgresql://example.invalid/db")
    with pytest.raises(RuntimeError, match="Set the SECRET_KEY"):
        settings_module.load_settings()


def test_a_short_secret_key_is_refused(env):
    env.setenv("SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        settings_module.load_settings()


def test_a_long_enough_secret_key_is_used_as_given(env):
    key = "a-real-looking-production-key-0123456789abcdef"
    env.setenv("SECRET_KEY", key)
    env.setenv("RENDER", "true")
    assert settings_module.load_settings().secret_key == key
