from __future__ import annotations

import json

import pytest

from market_sentinel.intelligence.errors import IntelligenceMalformedError
from market_sentinel.intelligence.parse import parse_model_output

_ADVICE_PHRASES = (
    "建议继续持有",
    "可考虑逢低布局",
    "止损位已到",
    "看多后市",
    "目标价上看",
    "建议减持",
    "buy",
    "sell",
    "hold",
    "stop loss",
    "target price",
    "take profit",
    "entry",
    "exit",
    "position sizing",
    "go long",
    "go short",
    "买入",
    "卖出",
    "增持",
    "减仓",
    "建仓",
    "仓位",
    "做多",
    "做空",
    "看空",
    "抄底",
    "追涨",
    "逢低买入",
    "止盈",
    "加仓",
)


def _json(summary: str, reason: str = "tape") -> str:
    return json.dumps(
        {
            "worth_highlight": True,
            "reason": reason,
            "confidence": 0.5,
            "summary": summary,
        }
    )


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


@pytest.mark.parametrize("phrase", _ADVICE_PHRASES)
def test_actionable_trading_instruction_fail_closed(phrase: str) -> None:
    with pytest.raises(IntelligenceMalformedError, match="trading advice"):
        parse_model_output(_json(f"观察后{phrase}。"))
    with pytest.raises(IntelligenceMalformedError, match="trading advice"):
        parse_model_output(_json("descriptive tape", reason=phrase))


def test_descriptive_observation_is_allowed() -> None:
    row = parse_model_output(
        _json(
            "short-term range stayed tight along session VWAP.",
            reason="volume expanded without a breakout",
        )
    )
    assert "VWAP" in row.summary
