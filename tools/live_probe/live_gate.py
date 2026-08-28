from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from market_sentinel.health.policy import HealthPolicy
from tools.live_probe.common import Observation, high_low_plausible

CST = timezone(timedelta(hours=8))
PRIMARY_SYMBOLS = ("600519.SH", "000001.SZ")
TEN_SYMBOL_BATCH = (
    "600519.SH",
    "000001.SZ",
    "600036.SH",
    "601318.SH",
    "000858.SZ",
    "002415.SZ",
    "600276.SH",
    "000333.SZ",
    "601166.SH",
    "600900.SH",
)
TENCENT_LIVE_MIN_FIELDS = 80
SINA_LIVE_MIN_FIELDS = 32
MORNING_OPEN = time(9, 15)
MORNING_CLOSE = time(11, 30)
AFTERNOON_OPEN = time(13, 0)
AFTERNOON_CLOSE = time(15, 0)
STALE_LATENCY_S = 120.0


def cst_now(now: float | None = None) -> datetime:
    if now is None:
        return datetime.now(tz=CST)
    return datetime.fromtimestamp(now, tz=CST)


def quote_cst(obs: Observation) -> datetime:
    if obs.market_timestamp_parsed is None:
        raise ValueError("missing market timestamp")
    return datetime.fromtimestamp(obs.market_timestamp_parsed, tz=CST)


def in_cash_session(stamp: datetime) -> bool:
    clock = stamp.time()
    morning = MORNING_OPEN <= clock <= MORNING_CLOSE
    afternoon = AFTERNOON_OPEN <= clock <= AFTERNOON_CLOSE
    return morning or afternoon


def evaluate_quote(
    obs: Observation,
    *,
    today: date,
    min_fields: int,
    now: float | None = None,
) -> list[str]:
    failures: list[str] = []
    if not obs.name or not str(obs.name).strip():
        failures.append(f"{obs.symbol} name empty")
    if obs.price is None or obs.price <= 0:
        failures.append(f"{obs.symbol} price not positive")
    if obs.prev_close is None or obs.prev_close <= 0:
        failures.append(f"{obs.symbol} prev_close not positive")
    if obs.open is None or obs.high is None or obs.low is None:
        failures.append(f"{obs.symbol} missing open/high/low")
    elif not high_low_plausible(price=obs.price or 0.0, open_=obs.open, high=obs.high, low=obs.low)[
        0
    ]:
        failures.append(f"{obs.symbol} high/low not plausible")
    if obs.volume_raw is None or obs.volume_raw < 0:
        failures.append(f"{obs.symbol} volume negative")
    if obs.turnover_raw is None or obs.turnover_raw < 0:
        failures.append(f"{obs.symbol} amount negative")
    if obs.field_count is None or obs.field_count < min_fields:
        failures.append(f"{obs.symbol} field_count {obs.field_count} below expected {min_fields}")
    if obs.market_timestamp_parsed is None:
        failures.append(f"{obs.symbol} missing vendor timestamp")
        return failures
    quoted = quote_cst(obs)
    if quoted.date() != today:
        failures.append(
            f"{obs.symbol} quote date {quoted.date().isoformat()} != today {today.isoformat()}"
        )
    if not in_cash_session(quoted):
        failures.append(
            f"{obs.symbol} quote time {quoted.strftime('%H:%M:%S')} outside cash session"
        )
    if obs.received_minus_market_s is None:
        failures.append(f"{obs.symbol} latency not recorded")
    elif obs.received_minus_market_s > STALE_LATENCY_S:
        failures.append(f"{obs.symbol} latency {obs.received_minus_market_s:.1f}s looks stale")
    wall = cst_now(now)
    if (
        quoted.date() == today
        and wall.time() >= MORNING_OPEN
        and quoted < wall - timedelta(hours=2)
    ):
        failures.append(f"{obs.symbol} quote is more than 2h behind wall clock")
    return failures


def evaluate_series(rows: list[Observation]) -> list[str]:
    failures: list[str] = []
    if len(rows) < 2:
        return ["series too short"]
    positive = 0
    ts_advance = 0
    rewind = 0
    previous: Observation | None = None
    for row in rows:
        if previous is not None:
            if (
                row.volume_raw is not None
                and previous.volume_raw is not None
                and row.volume_raw + 1e-9 < previous.volume_raw
            ):
                failures.append(
                    f"{row.symbol} volume decreased {previous.volume_raw} -> {row.volume_raw}"
                )
            if (
                row.turnover_raw is not None
                and previous.turnover_raw is not None
                and row.turnover_raw + 1e-9 < previous.turnover_raw
            ):
                failures.append(
                    f"{row.symbol} amount decreased {previous.turnover_raw} -> {row.turnover_raw}"
                )
            if row.delta_volume is not None and row.delta_volume > 1e-9:
                positive += 1
            if (
                row.market_timestamp_parsed is not None
                and previous.market_timestamp_parsed is not None
            ):
                if row.market_timestamp_parsed > previous.market_timestamp_parsed + 1e-9:
                    ts_advance += 1
                elif row.market_timestamp_parsed + 1e-9 < previous.market_timestamp_parsed:
                    rewind += 1
        previous = row
    if rewind:
        failures.append(f"out-of-order timestamps: {rewind}")
    if positive == 0 and ts_advance == 0:
        failures.append(
            "no timestamp advancement and no positive volume/amount delta; "
            "all-zero idle is not success"
        )
    return failures


def delayed_s_unchanged() -> None:
    policy = HealthPolicy()
    if policy.delayed_s != 3.0:
        raise AssertionError(f"delayed_s changed to {policy.delayed_s}")
