from __future__ import annotations

import pytest

from market_sentinel.intelligence.errors import IntelligenceMalformedError
from market_sentinel.intelligence.parse import parse_model_output


def test_parses_structured_analyst_json() -> None:
    row = parse_model_output(
        '{"worth_highlight": true, "reason": "price and volume expanded", '
        '"confidence": 0.82, "summary": "Unusually strong expansion."}'
    )
    assert row.worth_highlight is True
    assert row.confidence == pytest.approx(0.82)
    assert "buy" not in row.summary.lower()


def test_malformed_and_trading_advice_fail_closed() -> None:
    with pytest.raises(IntelligenceMalformedError):
        parse_model_output("not-json")
    with pytest.raises(IntelligenceMalformedError):
        parse_model_output('{"worth_highlight": true}')
    with pytest.raises(IntelligenceMalformedError):
        parse_model_output(
            '{"worth_highlight": true, "reason": "x", "confidence": 1.2, "summary": "ok"}'
        )
    with pytest.raises(IntelligenceMalformedError):
        parse_model_output(
            '{"worth_highlight": true, "reason": "x", "confidence": 0.5, '
            '"summary": "you should buy"}'
        )
