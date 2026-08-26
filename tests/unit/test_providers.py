from pathlib import Path

from market_sentinel.clock import FakeClock
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.providers.replay import ReplayProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

TEN_SYMBOLS = [
    "600519.SH",
    "000001.SZ",
    "601318.SH",
    "000858.SZ",
    "601398.SH",
    "00700.HK",
    "00941.HK",
    "01299.HK",
    "02318.HK",
    "03690.HK",
]


async def test_fake_provider_fetches_ten_symbols() -> None:
    clock = FakeClock(wall=1_700_000_000.0)
    provider = FakeProvider(clock)
    snapshots = await provider.fetch_quotes(TEN_SYMBOLS)
    assert [item.symbol for item in snapshots] == TEN_SYMBOLS
    assert all(item.received_timestamp == 1_700_000_000.0 for item in snapshots)


async def test_fake_provider_omits_failed_symbol_without_raising() -> None:
    clock = FakeClock()
    provider = FakeProvider(clock)
    provider.fail_symbol("00700.HK")
    snapshots = await provider.fetch_quotes(["00700.HK", "600519.SH"])
    assert [item.symbol for item in snapshots] == ["600519.SH"]


async def test_fake_provider_timeout_raises() -> None:
    provider = FakeProvider(FakeClock())
    provider.set_timeout(True)
    try:
        await provider.fetch_quotes(["00700.HK"])
    except TimeoutError:
        return
    raise AssertionError("expected TimeoutError")


async def test_replay_provider_plays_fixture_ticks() -> None:
    clock = FakeClock(wall=1_700_000_200.0)
    provider = ReplayProvider(FIXTURES / "replay_quotes.jsonl", clock)
    first = await provider.fetch_quotes(["00700.HK", "600519.SH"])
    second = await provider.fetch_quotes(["00700.HK", "600519.SH"])
    exhausted = await provider.fetch_quotes(["00700.HK", "600519.SH"])
    assert [item.price for item in first] == [600.0, 1480.0]
    assert [item.price for item in second] == [602.5]
    assert exhausted == []
    assert first[0].received_timestamp == 1_700_000_200.0
