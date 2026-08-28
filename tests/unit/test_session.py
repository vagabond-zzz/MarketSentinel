from datetime import datetime, timedelta, timezone

from market_sentinel.market_data.session import (
    cash_session_overlap_s,
    is_a_share_symbol,
    session_id,
)

CST = timezone(timedelta(hours=8))


def test_cash_session_excludes_lunch() -> None:
    start = datetime(2024, 1, 15, 11, 0, tzinfo=CST).timestamp()
    end = datetime(2024, 1, 15, 14, 0, tzinfo=CST).timestamp()
    # 11:00–11:30 + 13:00–14:00 = 5400s; lunch 11:30–13:00 excluded
    assert cash_session_overlap_s(start, end) == 5400.0


def test_cash_session_full_cash_day() -> None:
    start = datetime(2024, 1, 15, 9, 30, tzinfo=CST).timestamp()
    end = datetime(2024, 1, 15, 15, 0, tzinfo=CST).timestamp()
    assert cash_session_overlap_s(start, end) == 14400.0


def test_cash_session_overnight_excluded() -> None:
    start = datetime(2024, 1, 15, 15, 0, tzinfo=CST).timestamp()
    end = datetime(2024, 1, 16, 9, 30, tzinfo=CST).timestamp()
    assert cash_session_overlap_s(start, end) == 0.0


def test_cash_session_one_timestamp_is_zero() -> None:
    stamp = datetime(2024, 1, 15, 10, 0, tzinfo=CST).timestamp()
    assert cash_session_overlap_s(stamp, stamp) == 0.0


def test_session_id_is_utc8_date() -> None:
    stamp = datetime(2024, 1, 15, 10, 0, tzinfo=CST).timestamp()
    assert session_id(stamp) == "2024-01-15"


def test_cash_session_swaps_inverted_range() -> None:
    start = datetime(2024, 1, 15, 14, 0, tzinfo=CST).timestamp()
    end = datetime(2024, 1, 15, 10, 0, tzinfo=CST).timestamp()
    assert cash_session_overlap_s(start, end) == cash_session_overlap_s(end, start)
    assert cash_session_overlap_s(end, start) == 9000.0


def test_cash_session_spans_next_morning() -> None:
    start = datetime(2024, 1, 15, 14, 0, tzinfo=CST).timestamp()
    end = datetime(2024, 1, 16, 10, 0, tzinfo=CST).timestamp()
    # 14:00–15:00 + 09:30–10:00 = 5400s
    assert cash_session_overlap_s(start, end) == 5400.0


def test_cash_session_saturday_is_zero() -> None:
    start = datetime(2024, 1, 13, 9, 30, tzinfo=CST).timestamp()
    end = datetime(2024, 1, 13, 15, 0, tzinfo=CST).timestamp()
    assert cash_session_overlap_s(start, end) == 0.0


def test_cash_session_friday_to_monday_skips_weekend() -> None:
    start = datetime(2024, 1, 12, 14, 0, tzinfo=CST).timestamp()
    end = datetime(2024, 1, 15, 10, 0, tzinfo=CST).timestamp()
    # Friday 14:00–15:00 + Monday 09:30–10:00 = 5400s
    assert cash_session_overlap_s(start, end) == 5400.0


def test_is_a_share_symbol_sh_sz_only() -> None:
    assert is_a_share_symbol("600519.SH") is True
    assert is_a_share_symbol("000001.SZ") is True
    assert is_a_share_symbol("00700.HK") is False
    assert is_a_share_symbol("AAPL") is False
