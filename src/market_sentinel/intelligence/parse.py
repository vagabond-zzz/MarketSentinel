from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from market_sentinel.intelligence.errors import IntelligenceMalformedError

_ADVICE = re.compile(
    r"\b(buy|sell|bought|sold)\b|买入|卖出|做多|做空|加仓|减仓",
    re.IGNORECASE,
)
_REQUIRED = ("worth_highlight", "reason", "confidence", "summary")


@dataclass(frozen=True)
class ModelCompletion:
    worth_highlight: bool
    reason: str
    confidence: float
    summary: str


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
    if _ADVICE.search(reason) or _ADVICE.search(summary):
        raise IntelligenceMalformedError("trading advice is not allowed")
    return ModelCompletion(
        worth_highlight=worth,
        reason=reason.strip(),
        confidence=float(confidence),
        summary=summary.strip(),
    )
