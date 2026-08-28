from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from market_sentinel.intelligence.errors import IntelligenceMalformedError

_REQUIRED = ("worth_highlight", "reason", "confidence", "summary")

# English tokens use letter-boundaries so "观察后buy。" still matches, while
# "short-term" / "along" / "threshold" do not become trading advice.
_EN_ADVICE = re.compile(
    r"(?<![A-Za-z])(?:buy|sell|bought|sold|hold)(?![A-Za-z])"
    r"|(?<![A-Za-z])(?:entry|exit)(?![A-Za-z])"
    r"|(?<![A-Za-z])stop\s+loss(?:es)?(?![A-Za-z])"
    r"|(?<![A-Za-z])take\s+profit(?![A-Za-z])"
    r"|(?<![A-Za-z])target\s+price(?![A-Za-z])"
    r"|(?<![A-Za-z])position\s+siz(?:e|ing)(?![A-Za-z])"
    r"|(?<![A-Za-z])go\s+long(?![A-Za-z])"
    r"|(?<![A-Za-z])go\s+short(?![A-Za-z])"
    r"|(?<![A-Za-z])long\s+position(?![A-Za-z])"
    r"|(?<![A-Za-z])short\s+position(?![A-Za-z])",
    re.IGNORECASE,
)

_ZH_ADVICE = re.compile(
    "买入|卖出|持有|增持|减持|加仓|减仓|建仓|仓位|"
    "做多|做空|看多|看空|抄底|追涨|逢低|"
    "止损|止盈|目标价|布局"
)


@dataclass(frozen=True)
class ModelCompletion:
    worth_highlight: bool
    reason: str
    confidence: float
    summary: str
    token_in: int | None = None
    token_out: int | None = None


def contains_trading_advice(text: str) -> bool:
    return _EN_ADVICE.search(text) is not None or _ZH_ADVICE.search(text) is not None


def parse_model_output(text: str) -> ModelCompletion:
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IntelligenceMalformedError("model output is not JSON") from exc
    if not isinstance(data, dict):
        raise IntelligenceMalformedError("model output is not an object")
    missing = [key for key in _REQUIRED if key not in data]
    if missing:
        raise IntelligenceMalformedError("model output missing fields")
    worth = data["worth_highlight"]
    if not isinstance(worth, bool):
        raise IntelligenceMalformedError("worth_highlight must be bool")
    reason = data["reason"]
    summary = data["summary"]
    confidence = data["confidence"]
    if not isinstance(reason, str) or not reason.strip():
        raise IntelligenceMalformedError("reason must be a non-empty string")
    if not isinstance(summary, str) or not summary.strip():
        raise IntelligenceMalformedError("summary must be a non-empty string")
    if not isinstance(confidence, int | float) or isinstance(confidence, bool):
        raise IntelligenceMalformedError("confidence must be a number")
    if not 0.0 <= float(confidence) <= 1.0:
        raise IntelligenceMalformedError("confidence out of range")
    if contains_trading_advice(reason) or contains_trading_advice(summary):
        raise IntelligenceMalformedError("trading advice is not allowed")
    return ModelCompletion(
        worth_highlight=worth,
        reason=reason.strip(),
        confidence=float(confidence),
        summary=summary.strip(),
    )
