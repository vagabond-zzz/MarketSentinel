import json
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
    first = await provider.fetch_quotes(["000001.SZ", "600519.SH"])
    second = await provider.fetch_quotes(["000001.SZ", "600519.SH"])
    exhausted = await provider.fetch_quotes(["000001.SZ", "600519.SH"])
    assert [item.price for item in first] == [11.2, 1480.0]
    assert [item.price for item in second] == [11.25]
    assert exhausted == []
    assert first[0].received_timestamp == 1_700_000_200.0
    assert provider.source_exhausted() is True


async def test_replay_source_exhausted_is_false_before_eof() -> None:
    clock = FakeClock(wall=1_700_000_200.0)
    provider = ReplayProvider(FIXTURES / "replay_quotes.jsonl", clock)
    assert provider.source_exhausted() is False
    await provider.fetch_quotes(["000001.SZ"])
    assert provider.source_exhausted() is False


def test_replay_fixture_corpus_is_a_share_only() -> None:
    for path in sorted(FIXTURES.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            for row in json.loads(line):
                assert row["symbol"].endswith((".SH", ".SZ")), (path.name, row["symbol"])


async def test_multi_a_share_ui_fixture_returns_three_symbols() -> None:
    clock = FakeClock(wall=1_700_000_200.0)
    provider = ReplayProvider(FIXTURES / "multi_a_share_ui.jsonl", clock)
    symbols = ["600519.SH", "000001.SZ", "300750.SZ"]
    first = await provider.fetch_quotes(symbols)
    assert [item.symbol for item in first] == symbols
    assert [item.price for item in first] == [1500.0, 11.20, 220.0]
