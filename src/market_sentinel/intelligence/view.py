from __future__ import annotations

from market_sentinel.intelligence.contract import (
    FallbackReason,
    IntelligenceResult,
    IntelligenceStatus,
)


def intelligence_view(result: IntelligenceResult | None, signal_id: str) -> IntelligenceResult:
    if result is not None:
        return result
    return IntelligenceResult(
        signal_id=signal_id,
        status=IntelligenceStatus.NOT_REQUESTED,
        requested=False,
        annotation=None,
        fallback_reason=FallbackReason.NONE,
        model_calls=0,
    )
