import logging

from market_sentinel.clock import FakeClock
from market_sentinel.intelligence.bootstrap import optional_intelligence
from market_sentinel.intelligence.fake import FakeIntelligenceProvider


def test_intelligence_sidecar_is_off_by_default() -> None:
    assert optional_intelligence(FakeClock(), environ={}) is None


def test_intelligence_sidecar_can_enable_fake_without_network() -> None:
    coord = optional_intelligence(
        FakeClock(),
        environ={"MARKET_SENTINEL_INTEL_ENABLED": "1", "MARKET_SENTINEL_INTEL_PROVIDER": "fake"},
    )
    assert coord is not None
    assert isinstance(coord._provider, FakeIntelligenceProvider)
    assert coord._timeout_s == 8.0


def test_enabled_without_api_key_disables_sidecar_and_keeps_core(caplog) -> None:
    caplog.set_level(logging.WARNING)
    coord = optional_intelligence(
        FakeClock(),
        environ={
            "MARKET_SENTINEL_INTEL_ENABLED": "1",
            "MARKET_SENTINEL_INTEL_PROVIDER": "dashscope",
        },
    )
    assert coord is None
    text = caplog.text
    assert "intelligence" in text.lower()
    assert "sk-" not in text
    assert "DASHSCOPE_API_KEY=" not in text


def test_unknown_provider_disables_sidecar(caplog) -> None:
    caplog.set_level(logging.WARNING)
    coord = optional_intelligence(
        FakeClock(),
        environ={
            "MARKET_SENTINEL_INTEL_ENABLED": "1",
            "MARKET_SENTINEL_INTEL_PROVIDER": "not-a-vendor",
        },
    )
    assert coord is None
    assert "not-a-vendor" in caplog.text or "unknown" in caplog.text.lower()
