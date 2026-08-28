from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TextIO

from market_sentinel import __version__
from market_sentinel.domain.models import WatchItem
from market_sentinel.errors import WatchlistFullError, WatchlistSymbolError
from market_sentinel.ipc.codec import decode_line, encode_error, encode_message
from market_sentinel.ipc.mapping import map_engine_state, map_tick_alerts
from market_sentinel.ipc.protocol import HOST_COMMANDS, DaemonPhase, ErrorCode
from market_sentinel.ipc.writer import ProtocolWriter
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.runtime.results import EngineTickResult
from market_sentinel.telemetry.host_interaction import parse_host_interaction

logger = logging.getLogger(__name__)

_IDLE_WAIT_S = 0.05


class MarketDaemon:
    """JSONL stdio daemon wrapping MarketEngine.

    stdin is read with ``asyncio.to_thread(readline)`` so Windows pipes work.
    Commands and ticks share one lock: a watchlist replace is never visible
    mid-tick and takes effect on the next full tick.
    """

    def __init__(
        self,
        engine: MarketEngine,
        *,
        stdin: TextIO,
        stdout: TextIO,
        readline: Callable[[], str] | None = None,
    ) -> None:
        self._engine = engine
        self._readline = readline or stdin.readline
        self._writer = ProtocolWriter(stdout)
        self._lock = asyncio.Lock()
        self._phase = DaemonPhase.AWAITING_HELLO
        self._shutdown = asyncio.Event()

    @property
    def phase(self) -> DaemonPhase:
        return self._phase

    async def run(self) -> int:
        if self._engine.intelligence is not None:
            await self._engine.intelligence.start()
        ticker = asyncio.create_task(self._tick_loop(), name="market-daemon-tick")
        try:
            await self._stdin_loop()
        finally:
            self._phase = DaemonPhase.SHUTTING_DOWN
            self._shutdown.set()
            ticker.cancel()
            try:
                await ticker
            except asyncio.CancelledError:
                pass
            if self._engine.intelligence is not None:
                await self._engine.intelligence.shutdown()
            closer = getattr(self._engine.telemetry, "close", None)
            if callable(closer):
                closer()
        return 0

    async def _stdin_loop(self) -> None:
        while not self._shutdown.is_set():
            line = await asyncio.to_thread(self._readline)
            if line == "":
                async with self._lock:
                    await self._shutdown_locked(request_id=None)
                return
            async with self._lock:
                self._dispatch_line(line)
                if self._phase is DaemonPhase.SHUTTING_DOWN:
                    return

    async def _tick_loop(self) -> None:
        try:
            while not self._shutdown.is_set():
                wait = _IDLE_WAIT_S
                async with self._lock:
                    if self._phase is DaemonPhase.SHUTTING_DOWN:
                        return
                    if self._phase is DaemonPhase.RUNNING:
                        result = await self._engine.tick()
                        self._emit_tick(result)
                        wait = self._engine.scheduler.next_wait_s(
                            self._engine.watchlist.enabled_symbols()
                        )
                await asyncio.sleep(wait)
        except asyncio.CancelledError:
            return

    def _emit_tick(self, result: EngineTickResult) -> None:
        self._writer.send(encode_message("state", state=map_engine_state(self._engine).to_wire()))
        candidates, market_timestamp = map_tick_alerts(result)
        if candidates:
            self._writer.send(
                encode_message(
                    "alert",
                    candidates=[item.to_wire() for item in candidates],
                    market_timestamp=market_timestamp,
                )
            )

    def _dispatch_line(self, line: str) -> None:
        command, error = decode_line(line)
        if error is not None:
            self._writer.send(error)
            return
        if command is None:
            return
        message_type = command["type"]
        request_id = command.get("request_id")
        if message_type not in HOST_COMMANDS:
            self._writer.send(
                encode_error(
                    ErrorCode.UNKNOWN_TYPE,
                    f"unknown type: {message_type}",
                    request_id=request_id if isinstance(request_id, str) else None,
                )
            )
            return
        if not isinstance(request_id, str) or not request_id:
            self._writer.send(encode_error(ErrorCode.MISSING_REQUEST_ID, "request_id is required"))
            return
        if message_type == "shutdown":
            self._shutdown_sync(request_id)
            return
        if self._phase is DaemonPhase.SHUTTING_DOWN:
            self._writer.send(
                encode_error(
                    ErrorCode.SHUTTING_DOWN,
                    "daemon is shutting down",
                    request_id=request_id,
                )
            )
            return
        handler = {
            "hello": self._hello,
            "start": self._start,
            "pause": self._pause,
            "resume": self._resume,
            "set_watchlist": self._set_watchlist,
            "get_state": self._get_state,
            "host_interaction": self._host_interaction,
        }[message_type]
        handler(command, request_id)

    def _require_ready(self, request_id: str) -> bool:
        if self._phase is DaemonPhase.AWAITING_HELLO:
            self._writer.send(
                encode_error(
                    ErrorCode.NOT_READY,
                    "hello is required first",
                    request_id=request_id,
                )
            )
            return False
        return True

    def _hello(self, command: dict[str, Any], request_id: str) -> None:
        del command
        if self._phase is DaemonPhase.AWAITING_HELLO:
            self._phase = DaemonPhase.READY
        self._writer.send(encode_message("ready", request_id=request_id, core_version=__version__))

    def _start(self, command: dict[str, Any], request_id: str) -> None:
        del command
        if not self._require_ready(request_id):
            return
        if self._phase is DaemonPhase.PAUSED:
            self._writer.send(
                encode_error(
                    ErrorCode.PAUSED,
                    "daemon is paused; send resume",
                    request_id=request_id,
                )
            )
            return
        self._phase = DaemonPhase.RUNNING
        self._writer.send(encode_message("ack", request_id=request_id))

    def _pause(self, command: dict[str, Any], request_id: str) -> None:
        del command
        if not self._require_ready(request_id):
            return
        if self._phase is DaemonPhase.READY:
            self._writer.send(
                encode_error(
                    ErrorCode.NOT_STARTED,
                    "start is required before pause",
                    request_id=request_id,
                )
            )
            return
        self._phase = DaemonPhase.PAUSED
        self._writer.send(encode_message("ack", request_id=request_id))

    def _resume(self, command: dict[str, Any], request_id: str) -> None:
        del command
        if not self._require_ready(request_id):
            return
        if self._phase is DaemonPhase.READY:
            self._writer.send(
                encode_error(
                    ErrorCode.NOT_STARTED,
                    "start is required before resume",
                    request_id=request_id,
                )
            )
            return
        self._phase = DaemonPhase.RUNNING
        self._writer.send(encode_message("ack", request_id=request_id))

    def _set_watchlist(self, command: dict[str, Any], request_id: str) -> None:
        if not self._require_ready(request_id):
            return
        items_raw = command.get("items")
        if not isinstance(items_raw, list):
            self._writer.send(
                encode_error(
                    ErrorCode.INVALID_PAYLOAD,
                    "items must be a list",
                    request_id=request_id,
                )
            )
            return
        parsed: list[WatchItem] = []
        for raw in items_raw:
            if (
                not isinstance(raw, dict)
                or not isinstance(raw.get("symbol"), str)
                or not raw["symbol"]
            ):
                self._writer.send(
                    encode_error(
                        ErrorCode.INVALID_PAYLOAD,
                        "each item needs a non-empty symbol",
                        request_id=request_id,
                    )
                )
                return
            enabled = raw.get("enabled", True)
            if not isinstance(enabled, bool):
                self._writer.send(
                    encode_error(
                        ErrorCode.INVALID_PAYLOAD,
                        "enabled must be a boolean",
                        request_id=request_id,
                    )
                )
                return
            parsed.append(WatchItem(symbol=raw["symbol"], enabled=enabled))
        try:
            self._engine.watchlist.replace(parsed)
        except WatchlistFullError as exc:
            self._writer.send(
                encode_error(ErrorCode.WATCHLIST_FULL, str(exc), request_id=request_id)
            )
            return
        except WatchlistSymbolError as exc:
            self._writer.send(
                encode_error(ErrorCode.DUPLICATE_SYMBOL, str(exc), request_id=request_id)
            )
            return
        self._writer.send(
            encode_message(
                "ack",
                request_id=request_id,
                watchlist_count=len(self._engine.watchlist.list()),
            )
        )

    def _get_state(self, command: dict[str, Any], request_id: str) -> None:
        del command
        if not self._require_ready(request_id):
            return
        self._writer.send(
            encode_message(
                "state",
                request_id=request_id,
                state=map_engine_state(self._engine).to_wire(),
            )
        )

    def _host_interaction(self, command: dict[str, Any], request_id: str) -> None:
        if not self._require_ready(request_id):
            return
        parsed = parse_host_interaction(command)
        if isinstance(parsed, str):
            self._writer.send(
                encode_error(ErrorCode.INVALID_PAYLOAD, parsed, request_id=request_id)
            )
            return
        payload: dict[str, object] = {
            "signal_id": parsed.signal_id,
            "host_action": parsed.host_action,
        }
        if parsed.created_timestamp is not None:
            payload["created_timestamp"] = parsed.created_timestamp
        self._engine.telemetry.emit(parsed.name, **payload)
        self._writer.send(encode_message("ack", request_id=request_id))

    def _shutdown_sync(self, request_id: str | None) -> None:
        self._phase = DaemonPhase.SHUTTING_DOWN
        self._shutdown.set()
        logger.info("daemon shutting down")
        self._writer.send(encode_message("shutdown_ack", request_id=request_id))

    async def _shutdown_locked(self, request_id: str | None) -> None:
        self._shutdown_sync(request_id)
