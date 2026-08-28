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
