export const PROTOCOL_VERSION = 1 as const;

export type SchedulerLevel = "COLD" | "WARM" | "HOT";
export type FeedStatus = "LIVE" | "DELAYED" | "STALE" | "DISCONNECTED";
export type EventDirection = "up" | "down" | "none";
export type SignalPriority = "info" | "notice" | "important" | "critical";
export type IntelligenceStatus =
  | "not_requested"
  | "queued"
  | "running"
  | "enriched"
  | "fallback";

export interface WireIntelligence {
  status: IntelligenceStatus;
  summary?: string;
  reason?: string;
  confidence?: number;
  fallback_reason?: string;
  worth_highlight?: boolean;
}

export interface WireSignal {
  id: string;
  family: string;
  direction: EventDirection;
  priority: SignalPriority;
  title: string;
  summary: string;
  intelligence?: WireIntelligence;
}

export type HostCommandType =
  | "hello"
  | "start"
  | "pause"
  | "resume"
  | "set_watchlist"
  | "get_state"
  | "shutdown";

export type CoreMessageType =
  | "ready"
  | "ack"
  | "error"
  | "state"
  | "alert"
  | "shutdown_ack";

export interface WatchlistItem {
  symbol: string;
  enabled: boolean;
}

export interface WireSymbolState {
  symbol: string;
  price: number | null;
  scheduler_level: SchedulerLevel;
  feed_status: FeedStatus;
  change_1m: number | null;
  change_5m: number | null;
  change_15m: number | null;
  volume_ratio_1m: number | null;
  volume_ratio_5m: number | null;
  ema5: number | null;
  ema20: number | null;
  rsi14: number | null;
  vwap: number | null;
  active_signals: WireSignal[];
}

export interface WireMarketState {
  watchlist_count: number;
  feed_status: FeedStatus;
  symbols: WireSymbolState[];
}

export interface WireAlertCandidate {
  id: string;
  symbol: string;
  family: string;
  direction: EventDirection;
  priority: SignalPriority;
  title: string;
  summary: string;
}

export interface HelloCommand {
  protocol_version: 1;
  type: "hello";
  request_id: string;
  host?: string;
  host_version?: string;
}

export interface StartCommand {
  protocol_version: 1;
  type: "start";
  request_id: string;
}

export interface PauseCommand {
  protocol_version: 1;
  type: "pause";
  request_id: string;
}

export interface ResumeCommand {
  protocol_version: 1;
  type: "resume";
  request_id: string;
}

export interface SetWatchlistCommand {
  protocol_version: 1;
  type: "set_watchlist";
  request_id: string;
  items: WatchlistItem[];
}

export interface GetStateCommand {
  protocol_version: 1;
  type: "get_state";
  request_id: string;
}

export interface ShutdownCommand {
  protocol_version: 1;
  type: "shutdown";
  request_id: string;
}

export type HostCommand =
  | HelloCommand
  | StartCommand
  | PauseCommand
  | ResumeCommand
  | SetWatchlistCommand
  | GetStateCommand
  | ShutdownCommand;

export type HostCommandBody =
  | { type: "hello"; host?: string; host_version?: string }
  | { type: "start" }
  | { type: "pause" }
  | { type: "resume" }
  | { type: "set_watchlist"; items: WatchlistItem[] }
  | { type: "get_state" }
  | { type: "shutdown" };

export interface ReadyMessage {
  protocol_version: 1;
  type: "ready";
  request_id: string;
  core_version: string;
}

export interface AckMessage {
  protocol_version: 1;
  type: "ack";
  request_id: string;
  watchlist_count?: number;
}

export interface ErrorMessage {
  protocol_version: 1;
  type: "error";
  request_id?: string;
  code: string;
  message: string;
}

export interface StateMessage {
  protocol_version: 1;
  type: "state";
  request_id?: string;
  state: WireMarketState;
}

export interface AlertMessage {
  protocol_version: 1;
  type: "alert";
  request_id?: string;
  candidates: WireAlertCandidate[];
  market_timestamp: number | null;
}

export interface ShutdownAckMessage {
  protocol_version: 1;
  type: "shutdown_ack";
  request_id?: string;
}

export type CoreMessage =
  | ReadyMessage
  | AckMessage
  | ErrorMessage
  | StateMessage
  | AlertMessage
  | ShutdownAckMessage;

export type RequestSuccessMessage = ReadyMessage | AckMessage | StateMessage | ShutdownAckMessage;

export const EXPECTED_RESPONSE: Record<HostCommandType, RequestSuccessMessage["type"]> = {
  hello: "ready",
  start: "ack",
  pause: "ack",
  resume: "ack",
  set_watchlist: "ack",
  get_state: "state",
  shutdown: "shutdown_ack",
};
