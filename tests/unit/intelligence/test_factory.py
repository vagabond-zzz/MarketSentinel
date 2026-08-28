import pytest

from market_sentinel.intelligence.errors import IntelligenceAuthError
from market_sentinel.intelligence.factory import create_intelligence_provider
from market_sentinel.intelligence.fake import FakeIntelligenceProvider


def test_factory_default_tests_use_fake_not_network() -> None:
    provider = create_intelligence_provider("fake", environ={})
    assert isinstance(provider, FakeIntelligenceProvider)


def test_factory_dashscope_without_key_fails_closed() -> None:
    with pytest.raises(IntelligenceAuthError, match="not set"):
        create_intelligence_provider("dashscope", environ={})
    with pytest.raises(ValueError, match="unknown"):
        create_intelligence_provider("unknown", environ={})
