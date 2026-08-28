from __future__ import annotations

import time

import pytest
from tools.live_probe.live_gate import (
    CST,
    PRIMARY_SYMBOLS,
    SINA_LIVE_MIN_FIELDS,
    TEN_SYMBOL_BATCH,
    TENCENT_LIVE_MIN_FIELDS,
    delayed_s_unchanged,
    evaluate_quote,
    evaluate_series,
)
from tools.live_probe.sina_probe import fetch_sina_quotes
from tools.live_probe.tencent_probe import fetch_tencent_quotes, run_samples

pytestmark = pytest.mark.live


def test_tencent_live_one_symbol_session_freshness() -> None:
    delayed_s_unchanged()
    today = __import__("datetime").datetime.now(tz=CST).date()
    rows = run_samples(
        ["600519.SH"],
        interval_s=2.0,
        count=6,
        sleep=time.sleep,
        now=time.time,
    )
    assert len(rows) == 6
    failures: list[str] = []
    for row in rows:
        assert row.symbol == "600519.SH"
        failures.extend(evaluate_quote(row, today=today, min_fields=TENCENT_LIVE_MIN_FIELDS))
    failures.extend(evaluate_series(rows))
    assert not failures, "\n".join(failures)


def test_tencent_live_batches_1_2_10() -> None:
    delayed_s_unchanged()
    today = __import__("datetime").datetime.now(tz=CST).date()
    batches = (
        list(PRIMARY_SYMBOLS[:1]),
        list(PRIMARY_SYMBOLS[:2]),
        list(TEN_SYMBOL_BATCH),
    )
    for symbols in batches:
        rows = fetch_tencent_quotes(symbols)
        assert [row.symbol for row in rows] == symbols
        failures: list[str] = []
        for row in rows:
            failures.extend(evaluate_quote(row, today=today, min_fields=TENCENT_LIVE_MIN_FIELDS))
        assert not failures, f"batch {len(symbols)}:\n" + "\n".join(failures)
        time.sleep(2.0)


def test_sina_live_crosscheck_once() -> None:
    delayed_s_unchanged()
    today = __import__("datetime").datetime.now(tz=CST).date()
    tencent = {row.symbol: row for row in fetch_tencent_quotes(list(PRIMARY_SYMBOLS))}
    sina = {row.symbol: row for row in fetch_sina_quotes(list(PRIMARY_SYMBOLS))}
    assert set(sina) == set(PRIMARY_SYMBOLS)
    failures: list[str] = []
    for symbol in PRIMARY_SYMBOLS:
        row = sina[symbol]
        failures.extend(evaluate_quote(row, today=today, min_fields=SINA_LIVE_MIN_FIELDS))
        other = tencent[symbol]
        if row.price and other.price:
            gap = abs(row.price - other.price) / other.price
            if gap > 0.02:
                failures.append(f"{symbol} sina/tencent price gap {gap:.4f}")
    assert not failures, "\n".join(failures)
