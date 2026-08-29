from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from market_sentinel.clock import FakeClock
from market_sentinel.errors import TuningConfigError
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.orchestration.warming import WarmingPolicy
from market_sentinel.providers.replay import ReplayProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.runtime.results import EngineTickResult
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.signals.composer import SignalComposer
from market_sentinel.signals.cooldown import CooldownGate
from market_sentinel.signals.pipeline import SignalPipeline
from market_sentinel.telemetry.collector import InMemoryTelemetryCollector
from market_sentinel.telemetry.runtime import TelemetryRuntime
from market_sentinel.tuning.config import OfflineTuningConfig
from market_sentinel.watchlist.watchlist import Watchlist

DEFAULT_CORPUS: tuple[str, ...] = (
    "normal_market",
    "rapid_move",
    "volume_spike",
    "price_volume_breakout",
    "reversal",
    "episode_lifecycle",
)

DEFAULT_REPLAY_SYMBOL = "600519.SH"


def default_fixture_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def validate_corpus(corpus: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    ids = tuple(corpus)
    if not ids:
        raise TuningConfigError("corpus must contain at least one corpus_id")
    if len(ids) != len(set(ids)):
        raise TuningConfigError("duplicate corpus_id")
    return ids


def corpus_fixture_path(fixture_dir: Path, corpus_id: str) -> Path:
    if "/" in corpus_id or "\\" in corpus_id or ".." in corpus_id or corpus_id.strip() == "":
        raise TuningConfigError("corpus_id is not a filesystem path")
    path = fixture_dir / f"{corpus_id}.jsonl"
    if not path.is_file():
        raise TuningConfigError("unknown corpus_id")
    return path


def scheduler_policy_for_replay() -> SchedulerPolicy:
    """Always-due poll intervals; production dwells (not OfflineTuningConfig)."""
    production = SchedulerPolicy()
    return SchedulerPolicy(
        cold_interval_s=0.0,
        warm_interval_s=0.0,
        hot_interval_s=0.0,
        upgrade_dwell_s=production.upgrade_dwell_s,
        hot_downgrade_dwell_s=production.hot_downgrade_dwell_s,
        warm_downgrade_dwell_s=production.warm_downgrade_dwell_s,
    )


def build_tuned_engine(
    *,
    clock: FakeClock,
    watchlist: Watchlist,
    provider: ReplayProvider,
    config: OfflineTuningConfig,
    telemetry: TelemetryRuntime,
) -> MarketEngine:
    return MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock, scheduler_policy_for_replay()),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        pipeline=SignalPipeline(
            clock,
            composer=SignalComposer(clock, lookback_s=config.cluster_lookback_s),
            cooldown=CooldownGate(clock),
            telemetry=telemetry,
        ),
        warming=WarmingPolicy(config.warming_config()),
        telemetry=telemetry,
    )


def tick_facts(results: list[EngineTickResult], symbol: str) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for tick in results:
        item = tick.for_symbol(symbol)
        if item is None:
            continue
        rows.append(
            {
                "event_types": tuple(sorted(event.type.value for event in item.accepted_events)),
                "alert_count": len(item.alert_candidates),
                "priorities": tuple(signal.priority.value for signal in item.alert_candidates),
                "families": tuple(signal.family for signal in item.alert_candidates),
                "level": None if item.level_after is None else item.level_after.value,
            }
        )
    return tuple(rows)


@dataclass(frozen=True)
class TunedReplayResult:
    corpus_id: str
    records: tuple[dict[str, object], ...]
    facts: tuple[dict[str, object], ...]


async def run_tuned_replay(
    config: OfflineTuningConfig,
    corpus_id: str,
    *,
    fixture_dir: Path,
    work_dir: Path,
    symbol: str = DEFAULT_REPLAY_SYMBOL,
) -> TunedReplayResult:
    path = corpus_fixture_path(fixture_dir, corpus_id)
    batches = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not batches:
        raise TuningConfigError("empty replay corpus")
    start = float(batches[0][0]["market_timestamp"])
    clock = FakeClock(wall=start, monotonic=0.0)
    watchlist = Watchlist(work_dir / f"watchlist-{corpus_id}.json")
    watchlist.add(symbol)
    collector = InMemoryTelemetryCollector()
    telemetry = TelemetryRuntime(clock, collector)
    engine = build_tuned_engine(
        clock=clock,
        watchlist=watchlist,
        provider=ReplayProvider(path, clock),
        config=config,
        telemetry=telemetry,
    )
    results: list[EngineTickResult] = []
    for batch in batches:
        clock.set_wall(float(batch[0]["market_timestamp"]))
        results.append(await engine.tick())
    records = tuple(event.to_record() for event in collector.events)
    return TunedReplayResult(
        corpus_id=corpus_id, records=records, facts=tick_facts(results, symbol)
    )
