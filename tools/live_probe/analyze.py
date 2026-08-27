from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tools.live_probe.common import Observation, high_low_plausible


@dataclass
class Classified:
    label: str
    confidence: str
    detail: str
    extras: dict[str, object] = field(default_factory=dict)


def _finite_deltas(series: list[Observation], attr: str) -> list[float]:
    values: list[float] = []
    for row in series:
        item = getattr(row, attr)
        if item is not None:
            values.append(float(item))
    return values


def classify_volume(series: list[Observation]) -> Classified:
    if len(series) < 2:
        return Classified("UNKNOWN", "MEASURED", "need at least two samples")
    deltas = _finite_deltas(series[1:], "delta_volume")
    if not deltas:
        return Classified("UNKNOWN", "MEASURED", "no volume deltas")
    if any(delta < 0 for delta in deltas):
        return Classified("NOT_CUMULATIVE", "MEASURED", "observed a negative volume delta")
    if any(delta > 0 for delta in deltas):
        return Classified(
            "CONFIRMED_CUMULATIVE",
            "MEASURED",
            "non-decreasing with at least one increase",
        )
    return Classified(
        "LIKELY_CUMULATIVE",
        "MEASURED",
        "non-decreasing but no increase in this window (idle or after-hours)",
    )


def _turnover_over_volume_over_price(row: Observation) -> float | None:
    if row.turnover_div_volume_div_price is not None:
        return row.turnover_div_volume_div_price
    if row.price in (None, 0.0) or row.volume_raw in (None, 0.0) or row.turnover_raw is None:
        return None
    return (row.turnover_raw / row.volume_raw) / row.price


def classify_turnover(series: list[Observation]) -> Classified:
    ratios = [
        value for row in series if (value := _turnover_over_volume_over_price(row)) is not None
    ]
    if not ratios:
        return Classified("UNKNOWN", "MEASURED", "no turnover/volume/price triple")
    median = sorted(ratios)[len(ratios) // 2]
    if 0.85 <= median <= 1.15:
        return Classified(
            "COMMENSURATE_WITH_VOLUME", "MEASURED", f"median (t/v)/price={median:.4f}"
        )
    if 80 <= median <= 120 or 0.008 <= median <= 0.0125:
        return Classified(
            "UNIT_MISMATCH_LIKELY",
            "INFERRED",
            f"median (t/v)/price={median:.4f} (near x100 or /100)",
        )
    return Classified("UNKNOWN", "MEASURED", f"median (t/v)/price={median:.4f}")


def classify_volume_unit(
    *,
    price: float,
    volume_raw: float,
    turnover_raw: float,
) -> Classified:
    if price <= 0 or volume_raw <= 0 or turnover_raw <= 0:
        return Classified("UNKNOWN", "UNKNOWN", "non-positive inputs")
    ratio = (turnover_raw / volume_raw) / price
    if 0.85 <= ratio <= 1.15:
        return Classified("股", "INFERRED", f"(turnover/volume)/price={ratio:.4f} near 1")
    if 80 <= ratio <= 120:
        return Classified("手", "INFERRED", f"(turnover/volume)/price={ratio:.4f} near 100")
    if 0.008 <= ratio <= 0.0125:
        return Classified("UNKNOWN", "INFERRED", f"(turnover/volume)/price={ratio:.4f} near 0.01")
    return Classified("UNKNOWN", "INFERRED", f"(turnover/volume)/price={ratio:.4f}")


def classify_timestamp(series: list[Observation]) -> Classified:
    if not series:
        return Classified("UNKNOWN", "MEASURED", "no samples")
    parsed = [row.market_timestamp_parsed for row in series]
    if any(item is None for item in parsed):
        return Classified("INVALID_AS_MARKET_TIME", "MEASURED", "missing vendor timestamp")
    close_to_received = []
    for row in series:
        if row.market_timestamp_parsed is None:
            continue
        close_to_received.append(abs(row.market_timestamp_parsed - row.received_timestamp) < 0.05)
    if close_to_received and all(close_to_received):
        return Classified(
            "INVALID_AS_MARKET_TIME",
            "MEASURED",
            "market timestamp equals received clock",
        )
    stamps = [item for item in parsed if item is not None]
    older = any(stamps[index] < stamps[index - 1] for index in range(1, len(stamps)))
    advances = any(stamps[index] > stamps[index - 1] for index in range(1, len(stamps)))
    repeats = any(stamps[index] == stamps[index - 1] for index in range(1, len(stamps)))
    detail = f"advances={advances} repeats={repeats} older={older}"
    if older:
        return Classified("LIKELY_MARKET_TIME", "MEASURED", detail)
    return Classified("VALID_MARKET_TIME", "MEASURED", detail)


def classify_high_low(series: list[Observation]) -> Classified:
    notes: list[str] = []
    for row in series:
        if None in (row.price, row.open, row.high, row.low):
            return Classified("UNKNOWN", "MEASURED", "missing OHLC")
        ok, note = high_low_plausible(price=row.price, open_=row.open, high=row.high, low=row.low)
        if not ok:
            return Classified("UNKNOWN", "MEASURED", note)
        notes.append(note)
    return Classified("LIKELY", "INFERRED", notes[0] if notes else "no rows")


def cross_compare(
    left: list[Observation],
    right: list[Observation],
) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    left_last = {row.symbol: row for row in left}
    right_last = {row.symbol: row for row in right}
    for symbol in sorted(set(left_last) & set(right_last)):
        a = left_last[symbol]
        b = right_last[symbol]
        summary[symbol] = {
            "price_left": a.price,
            "price_right": b.price,
            "volume_left": a.volume_raw,
            "volume_right": b.volume_raw,
            "turnover_left": a.turnover_raw,
            "turnover_right": b.turnover_raw,
            "market_ts_left": a.market_timestamp_parsed,
            "market_ts_right": b.market_timestamp_parsed,
            "freshness_left_s": a.received_minus_market_s,
            "freshness_right_s": b.received_minus_market_s,
        }
    return summary


def summarize(rows: list[Observation]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Observation]] = {}
    for row in rows:
        grouped.setdefault(f"{row.provider}:{row.symbol}", []).append(row)
    report: dict[str, dict[str, object]] = {}
    for key, series in grouped.items():
        report[key] = {
            "samples": len(series),
            "volume": asdict(classify_volume(series)),
            "turnover": asdict(classify_turnover(series)),
            "timestamp": asdict(classify_timestamp(series)),
            "high_low": asdict(classify_high_low(series)),
        }
        last = series[-1]
        if last.price and last.volume_raw and last.turnover_raw:
            report[key]["volume_unit"] = asdict(
                classify_volume_unit(
                    price=last.price,
                    volume_raw=last.volume_raw,
                    turnover_raw=last.turnover_raw,
                )
            )
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Classify live-probe JSONL. Not a MarketProvider.")
    parser.add_argument("--in", dest="input_path", required=True)
    args = parser.parse_args(argv)
    path = Path(args.input_path)
    rows: list[Observation] = []
    fields = set(Observation.__dataclass_fields__)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        rows.append(Observation(**{key: payload[key] for key in fields if key in payload}))
    print(json.dumps(summarize(rows), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
