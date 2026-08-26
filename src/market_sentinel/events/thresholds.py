from __future__ import annotations

# All price-change thresholds are decimal fractions (0.006 = 0.6%).
# Rules must never treat 0.6 as 0.6%.

RAPID_1M_SEV2 = 0.006  # 0.6%
RAPID_1M_SEV3 = 0.010  # 1.0%
RAPID_5M_SEV3 = 0.012  # 1.2%
RAPID_1M_SEV4 = 0.015  # 1.5%
RAPID_5M_SEV4 = 0.020  # 2.0%
RAPID_5M_SEV5 = 0.035  # 3.5%

VOL_5M_SEV2 = 1.8
VOL_5M_SEV3 = 2.5
VOL_1M_SEV3 = 3.0
VOL_5M_SEV4 = 4.0
VOL_5M_SEV5 = 6.0

BREAKOUT_SEV4 = 0.003  # 0.3% beyond previous session extreme
BREAKOUT_SEV5 = 0.008  # 0.8%

VWAP_CROSS_SEV3_5M = 0.008  # 0.8%

TTL_SHORT_S = 60.0
TTL_LONG_S = 120.0
