"""Generate small deterministic v0.2 replay JSONL fixtures. Run from repo root."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
T0 = datetime(2024, 1, 15, 9, 30, tzinfo=CST).timestamp()
SYM = "600519.SH"
OUT = Path(__file__).resolve().parent


def _quote(
    ts: float,
    price: float,
    *,
    high: float | None = None,
    low: float | None = None,
    volume: float,
    turnover: float | None = None,
) -> dict[str, float | str]:
    row: dict[str, float | str] = {
        "symbol": SYM,
        "price": price,
        "open": 100.0,
        "high": price if high is None else high,
        "low": price if low is None else low,
        "prev_close": 100.0,
        "volume": volume,
        "market_timestamp": ts,
    }
    if turnover is not None:
        row["turnover"] = turnover
    return row


def _write(name: str, quotes: list[dict[str, float | str]]) -> None:
    lines = [json.dumps([item], separators=(",", ":")) for item in quotes]
    (OUT / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _warmup(
    n: int = 26, *, high: float = 100.0, price: float = 100.0
) -> list[dict[str, float | str]]:
    quotes: list[dict[str, float | str]] = []
    volume = 1000.0
    for index in range(n):
        quotes.append(
            _quote(
                T0 + index * 60.0,
                price,
                high=high,
                low=price,
                volume=volume,
                turnover=volume * 100.0,
            )
        )
        volume += 10.0
    return quotes


def main() -> None:
    _write("normal_market.jsonl", _warmup(26, high=100.0, price=100.0))

    warm = [
        _quote(T0, 100.0, high=101.0, low=100.0, volume=1000.0),
        _quote(T0 + 60.0, 100.4, high=101.0, low=100.0, volume=1010.0),
    ]
    _write("pre_signal_warm.jsonl", warm)

    _write(
        "rapid_move.jsonl",
        [
            _quote(T0, 100.0, high=110.0, low=90.0, volume=1000.0, turnover=100_000.0),
            _quote(T0 + 60.0, 101.2, high=110.0, low=90.0, volume=1010.0, turnover=101_000.0),
            _quote(T0 + 61.0, 101.2, high=110.0, low=90.0, volume=1011.0, turnover=101_100.0),
        ],
    )

    spike = _warmup(26, high=100.0, price=100.0)
    last = spike[-1]
    spike.append(
        _quote(
            T0 + 26 * 60.0,
            100.0,
            high=100.0,
            low=100.0,
            volume=float(last["volume"]) + 500.0,
            turnover=(float(last["volume"]) + 500.0) * 100.0,
        )
    )
    _write("volume_spike.jsonl", spike)

    _write(
        "price_breakout.jsonl",
        [
            _quote(T0, 100.0, high=100.0, low=100.0, volume=1000.0, turnover=100_000.0),
            _quote(T0 + 60.0, 100.5, high=100.5, low=100.0, volume=1010.0, turnover=101_000.0),
        ],
    )

    combo = _warmup(26, high=100.4, price=100.0)
    combo.append(
        _quote(
            T0 + 26 * 60.0,
            100.8,
            high=100.8,
            low=100.0,
            volume=float(combo[-1]["volume"]) + 80.0,
            turnover=(float(combo[-1]["volume"]) + 80.0) * 100.8,
        )
    )
    combo.append(
        _quote(
            T0 + 26 * 60.0 + 1.0,
            100.8,
            high=100.85,
            low=100.0,
            volume=float(combo[-1]["volume"]) + 10.0,
            turnover=float(combo[-1]["turnover"]) + 1008.0,
        )
    )
    _write("price_volume_breakout.jsonl", combo)

    _write(
        "episode_lifecycle.jsonl",
        [
            _quote(T0, 100.0, high=110.0, low=90.0, volume=1000.0, turnover=100_000.0),
            _quote(T0 + 60.0, 101.2, high=110.0, low=90.0, volume=1010.0, turnover=101_000.0),
            _quote(T0 + 151.0, 101.2, high=110.0, low=90.0, volume=1020.0, turnover=102_000.0),
            _quote(T0 + 211.0, 102.5, high=110.0, low=90.0, volume=1030.0, turnover=103_000.0),
        ],
    )

    _write(
        "reversal.jsonl",
        [
            _quote(T0, 100.0, high=110.0, low=90.0, volume=1000.0, turnover=100_000.0),
            _quote(T0 + 60.0, 101.2, high=110.0, low=90.0, volume=1010.0, turnover=101_000.0),
            _quote(T0 + 70.0, 98.8, high=110.0, low=90.0, volume=1020.0, turnover=102_000.0),
        ],
    )

    _write(
        "tape_then_vwap.jsonl",
        [
            _quote(T0, 100.0, high=110.0, low=90.0, volume=1000.0, turnover=102_000.0),
            _quote(T0 + 60.0, 101.2, high=110.0, low=90.0, volume=1010.0, turnover=103_020.0),
            _quote(T0 + 70.0, 101.2, high=110.0, low=90.0, volume=1020.0, turnover=102_000.0),
        ],
    )


if __name__ == "__main__":
    main()
