"""Settings refuse to start on a placeholder signing key."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize("value", ["change-me", "", "   "])
def test_a_placeholder_signing_key_is_refused(value):
    """Shipping .env.example as-is would make every token forgeable."""
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(jwt_secret_key=value, _env_file=None)


def test_a_real_signing_key_is_accepted():
    assert Settings(jwt_secret_key="s3cret", _env_file=None).jwt_secret_key == "s3cret"


def test_openrouter_defaults_to_the_pinned_low_cost_instruction_model():
    settings = Settings(jwt_secret_key="s3cret", _env_file=None)

    assert settings.openrouter_model == "qwen/qwen3-30b-a3b-instruct-2507"
