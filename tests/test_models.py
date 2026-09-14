import pytest

from agent_service.models.provider import UnknownModelProviderError, get_model


def test_get_model_defaults_to_google_gemini():
    model = get_model()
    assert model.provider == "Google"


def test_get_model_unknown_provider_raises():
    with pytest.raises(UnknownModelProviderError):
        get_model(provider="does-not-exist")
