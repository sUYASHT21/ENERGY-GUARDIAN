import pytest
from pydantic import ValidationError

from app.config import INSECURE_DEFAULT_PASSWORD, INSECURE_DEFAULT_SECRET, Settings


def test_production_refuses_default_secrets():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(app_env="production", secret_key=INSECURE_DEFAULT_SECRET, admin_password="a-strong-password-123")
    with pytest.raises(ValidationError, match="ADMIN_PASSWORD"):
        Settings(app_env="production", secret_key="s" * 48, admin_password=INSECURE_DEFAULT_PASSWORD)


def test_production_accepts_strong_secrets_and_defaults_are_safe():
    s = Settings(app_env="production", secret_key="s" * 48, admin_password="a-strong-password-123")
    assert s.real_switching_enabled is False  # hardware switching is off unless explicitly enabled
    assert not s.using_insecure_defaults


def test_development_flags_insecure_defaults():
    assert Settings(app_env="development", secret_key=INSECURE_DEFAULT_SECRET).using_insecure_defaults
