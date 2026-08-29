import {
  PROTOCOL_VERSION,
  type CoreMessage,
  type CoreMessageType,
  type EventDirection,
  type FeedStatus,
  type IntelligenceStatus,
  type SchedulerLevel,
  type SignalPriority,
  type WireAlertCandidate,
  type WireIntelligence,
  type WireMarketState,
  type WireSignal,
  type WireSymbolState,
} from "./types";

const CORE_TYPES: readonly CoreMessageType[] = [
  "ready",
  "ack",
  "error",
  "state",
  "alert",
  "shutdown_ack",
];

const SCHEDULER_LEVELS: readonly SchedulerLevel[] = ["COLD", "WARM", "HOT"];
const FEED_STATUSES: readonly FeedStatus[] = ["LIVE", "DELAYED", "STALE", "DISCONNECTED"];
const DIRECTIONS: readonly EventDirection[] = ["up", "down", "none"];
const PRIORITIES: readonly SignalPriority[] = ["info", "notice", "important", "critical"];
const INTEL_STATUSES: readonly IntelligenceStatus[] = [
  "not_requested",
  "queued",
  "running",
  "enriched",
  "fallback",
];

export interface GuardFailure {
  ok: false;
  error: string;
  requestId?: string;
}

export interface GuardSuccess {
  ok: true;
  message: CoreMessage;
}

export type GuardResult = GuardSuccess | GuardFailure;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function peekRequestId(value: unknown): string | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  return typeof value.request_id === "string" && value.request_id.length > 0
    ? value.request_id
    : undefined;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNumberOrNull(value: unknown): value is number | null {
  return value === null || isFiniteNumber(value);
}

function readNumberOrNull(
  record: Record<string, unknown>,
  key: string,
): number | null | string {
  const value = record[key];
  if (!isNumberOrNull(value)) {
    return `${key} must be number or null`;
  }
  return value;
}

function readOptionalNumberOrNull(
  record: Record<string, unknown>,
  key: string,
): number | null | string {
  if (!(key in record) || record[key] === undefined) {
    return null;
  }
  return readNumberOrNull(record, key);
}

function readOptionalBool(
  record: Record<string, unknown>,
  key: string,
): boolean | string {
  if (!(key in record) || record[key] === undefined) {
    return false;
  }
  if (typeof record[key] !== "boolean") {
    return `${key} must be a boolean`;
  }
  return record[key];
}

function readOptionalBoolOrNull(
  record: Record<string, unknown>,
  key: string,
): boolean | null | string {
  if (!(key in record) || record[key] === undefined) {
    return null;
  }
  if (record[key] === null) {
    return null;
  }
  if (typeof record[key] !== "boolean") {
    return `${key} must be boolean or null`;
  }
  return record[key];
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function includes<T extends string>(allowed: readonly T[], value: unknown): value is T {
  return typeof value === "string" && (allowed as readonly string[]).includes(value);
}

function fail(error: string, value: unknown): GuardFailure {
  return { ok: false, error, requestId: peekRequestId(value) };
}

function parseIntelligence(value: unknown, label: string): WireIntelligence | string {
  if (!isRecord(value)) {
    return `${label} must be an object`;
  }
  if (!includes(INTEL_STATUSES, value.status)) {
    return `${label}.status is invalid`;
  }
  const intelligence: WireIntelligence = { status: value.status };
  if (value.summary !== undefined) {
    if (!isString(value.summary)) {
      return `${label}.summary must be a string`;
    }
    intelligence.summary = value.summary;
  }
  if (value.reason !== undefined) {
    if (!isString(value.reason)) {
      return `${label}.reason must be a string`;
    }
    intelligence.reason = value.reason;
  }
  if (value.fallback_reason !== undefined) {
    if (!isString(value.fallback_reason)) {
      return `${label}.fallback_reason must be a string`;
    }
    intelligence.fallback_reason = value.fallback_reason;
  }
  if (value.confidence !== undefined) {
    if (!isFiniteNumber(value.confidence)) {
      return `${label}.confidence must be a number`;
    }
    intelligence.confidence = value.confidence;
  }
  if (value.worth_highlight !== undefined) {
    if (typeof value.worth_highlight !== "boolean") {
      return `${label}.worth_highlight must be a boolean`;
    }
    intelligence.worth_highlight = value.worth_highlight;
  }
  return intelligence;
}

function parseSignal(value: unknown, label: string): WireSignal | string {
  if (!isRecord(value)) {
    return `${label} must be an object`;
  }
  if (
    !isString(value.id) ||
    !isString(value.family) ||
    !isString(value.title) ||
    !isString(value.summary)
  ) {
    return `${label} needs string id, family, title, summary`;
  }
  if (!includes(DIRECTIONS, value.direction)) {
    return `${label}.direction is invalid`;
  }
  if (!includes(PRIORITIES, value.priority)) {
    return `${label}.priority is invalid`;
  }
  let intelligence: WireIntelligence | undefined;
  if (value.intelligence !== undefined) {
    const parsed = parseIntelligence(value.intelligence, `${label}.intelligence`);
    if (typeof parsed === "string") {
      return parsed;
    }
    intelligence = parsed;
  }
  return {
    id: value.id,
    family: value.family,
    direction: value.direction,
    priority: value.priority,
    title: value.title,
    summary: value.summary,
    intelligence,
  };
}

function parseSymbolState(value: unknown): WireSymbolState | string {
  if (!isRecord(value)) {
    return "symbol state must be an object";
  }
  if (!isString(value.symbol)) {
    return "symbol is required";
  }
  if (!includes(SCHEDULER_LEVELS, value.scheduler_level)) {
    return "scheduler_level is invalid";
  }
  if (!includes(FEED_STATUSES, value.feed_status)) {
    return "feed_status is invalid";
  }
  const price = readNumberOrNull(value, "price");
  const change_1m = readNumberOrNull(value, "change_1m");
  const change_5m = readNumberOrNull(value, "change_5m");
  const change_15m = readNumberOrNull(value, "change_15m");
  const volume_ratio_1m = readNumberOrNull(value, "volume_ratio_1m");
  const volume_ratio_5m = readNumberOrNull(value, "volume_ratio_5m");
  const ema5 = readNumberOrNull(value, "ema5");
  const ema20 = readNumberOrNull(value, "ema20");
  const rsi14 = readNumberOrNull(value, "rsi14");
  const vwap = readNumberOrNull(value, "vwap");
  const change_day = readOptionalNumberOrNull(value, "change_day");
  const session_high_obs = readOptionalNumberOrNull(value, "session_high_obs");
  const session_low_obs = readOptionalNumberOrNull(value, "session_low_obs");
  const session_high_ref = readOptionalNumberOrNull(value, "session_high_ref");
  const session_low_ref = readOptionalNumberOrNull(value, "session_low_ref");
  const market_timestamp = readOptionalNumberOrNull(value, "market_timestamp");
  const above_vwap = readOptionalBoolOrNull(value, "above_vwap");
  if (typeof price === "string") return price;
  if (typeof change_1m === "string") return change_1m;
  if (typeof change_5m === "string") return change_5m;
  if (typeof change_15m === "string") return change_15m;
  if (typeof volume_ratio_1m === "string") return volume_ratio_1m;
  if (typeof volume_ratio_5m === "string") return volume_ratio_5m;
  if (typeof ema5 === "string") return ema5;
  if (typeof ema20 === "string") return ema20;
  if (typeof rsi14 === "string") return rsi14;
  if (typeof vwap === "string") return vwap;
  if (typeof change_day === "string") return change_day;
  if (typeof session_high_obs === "string") return session_high_obs;
  if (typeof session_low_obs === "string") return session_low_obs;
  if (typeof session_high_ref === "string") return session_high_ref;
  if (typeof session_low_ref === "string") return session_low_ref;
  if (typeof market_timestamp === "string") return market_timestamp;
  if (typeof above_vwap === "string") return above_vwap;
  if (!Array.isArray(value.active_signals)) {
    return "active_signals must be an array";
  }
  const active_signals: WireSignal[] = [];
  for (const [index, item] of value.active_signals.entries()) {
    const parsed = parseSignal(item, `active_signals[${index}]`);
    if (typeof parsed === "string") {
      return parsed;
    }
    active_signals.push(parsed);
  }
  return {
    symbol: value.symbol,
    price,
    scheduler_level: value.scheduler_level,
    feed_status: value.feed_status,
    change_1m,
    change_5m,
    change_15m,
    volume_ratio_1m,
    volume_ratio_5m,
    ema5,
    ema20,
    rsi14,
    vwap,
    active_signals,
    change_day,
    above_vwap,
    session_high_obs,
    session_low_obs,
    session_high_ref,
    session_low_ref,
    market_timestamp,
  };
}

function parseMarketState(value: unknown): WireMarketState | string {
  if (!isRecord(value)) {
    return "state payload must be an object";
  }
  if (!isFiniteNumber(value.watchlist_count)) {
    return "watchlist_count must be a number";
  }
  if (!includes(FEED_STATUSES, value.feed_status)) {
    return "state.feed_status is invalid";
  }
  if (!Array.isArray(value.symbols)) {
    return "symbols must be an array";
  }
  const symbols: WireSymbolState[] = [];
  for (const item of value.symbols) {
    const parsed = parseSymbolState(item);
    if (typeof parsed === "string") {
      return parsed;
    }
    symbols.push(parsed);
  }
  const intelligence_enabled = readOptionalBool(value, "intelligence_enabled");
  const replay_complete = readOptionalBool(value, "replay_complete");
  const last_market_timestamp = readOptionalNumberOrNull(value, "last_market_timestamp");
  if (typeof intelligence_enabled === "string") {
    return intelligence_enabled;
  }
  if (typeof replay_complete === "string") {
    return replay_complete;
  }
  if (typeof last_market_timestamp === "string") {
    return last_market_timestamp;
  }
  return {
    watchlist_count: value.watchlist_count,
    feed_status: value.feed_status,
    symbols,
    intelligence_enabled,
    replay_complete,
    last_market_timestamp,
  };
}

function parseCandidate(value: unknown, label: string): WireAlertCandidate | string {
  const parsed = parseSignal(value, label);
  if (typeof parsed === "string") {
    return parsed;
  }
  if (!isRecord(value) || !isString(value.symbol)) {
    return `${label}.symbol is required`;
  }
  return { ...parsed, symbol: value.symbol };
}

export function parseCoreMessage(value: unknown): GuardResult {
  if (!isRecord(value)) {
    return fail("message must be an object", value);
  }
  if (value.protocol_version !== PROTOCOL_VERSION) {
    return fail("unsupported protocol_version", value);
  }
  if (!includes(CORE_TYPES, value.type)) {
    return fail("unknown type", value);
  }
  const requestId = peekRequestId(value);
  switch (value.type) {
    case "ready": {
      if (requestId === undefined) {
        return fail("ready requires request_id", value);
      }
      if (!isString(value.core_version)) {
        return fail("ready requires core_version", value);
      }
      return {
        ok: true,
        message: {
          protocol_version: 1,
          type: "ready",
          request_id: requestId,
          core_version: value.core_version,
        },
      };
    }
    case "ack": {
      if (requestId === undefined) {
        return fail("ack requires request_id", value);
      }
      if (value.watchlist_count !== undefined && !isFiniteNumber(value.watchlist_count)) {
        return fail("ack.watchlist_count must be a number", value);
      }
      const message = {
        protocol_version: 1 as const,
        type: "ack" as const,
        request_id: requestId,
        ...(value.watchlist_count !== undefined ? { watchlist_count: value.watchlist_count } : {}),
      };
      return { ok: true, message };
    }
    case "error": {
      if (!isString(value.code) || !isString(value.message)) {
        return fail("error requires code and message", value);
      }
      const message: CoreMessage = {
        protocol_version: 1,
        type: "error",
        code: value.code,
        message: value.message,
      };
      if (requestId !== undefined) {
        message.request_id = requestId;
      }
      return { ok: true, message };
    }
    case "state": {
      const state = parseMarketState(value.state);
      if (typeof state === "string") {
        return fail(state, value);
      }
      const message: CoreMessage = {
        protocol_version: 1,
        type: "state",
        state,
      };
      if (requestId !== undefined) {
        message.request_id = requestId;
      }
      return { ok: true, message };
    }
    case "alert": {
      if (!Array.isArray(value.candidates)) {
        return fail("alert.candidates must be an array", value);
      }
      const candidates: WireAlertCandidate[] = [];
      for (const [index, item] of value.candidates.entries()) {
        const parsed = parseCandidate(item, `candidates[${index}]`);
        if (typeof parsed === "string") {
          return fail(parsed, value);
        }
        candidates.push(parsed);
      }
      if (!isNumberOrNull(value.market_timestamp)) {
        return fail("alert.market_timestamp must be number or null", value);
      }
      const message: CoreMessage = {
        protocol_version: 1,
        type: "alert",
        candidates,
        market_timestamp: value.market_timestamp,
      };
      if (requestId !== undefined) {
        message.request_id = requestId;
      }
      return { ok: true, message };
    }
    case "shutdown_ack": {
      const message: CoreMessage = { protocol_version: 1, type: "shutdown_ack" };
      if (requestId !== undefined) {
        message.request_id = requestId;
      }
      return { ok: true, message };
    }
    default:
      return fail("unknown type", value);
  }
}
