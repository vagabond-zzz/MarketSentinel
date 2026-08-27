import type { WatchlistItem } from "../protocol/types";

export type DesiredState = "RUNNING" | "PAUSED";

export type ActualState =
  | "STARTING"
  | "RUNNING"
  | "PAUSED"
  | "DISCONNECTED"
  | "STOPPING"
  | "STOPPED";

export type ProviderName = "fake" | "replay";

export interface HostConfig {
  coreRoot: string;
  uvPath: string;
  watchlist: WatchlistItem[];
  provider: ProviderName;
  replayPath?: string;
}

export interface RawSettings {
  coreRoot?: string;
  uvPath?: string;
  watchlist?: unknown;
  provider?: unknown;
  replayPath?: string;
}

export interface HostLogger {
  host(message: string): void;
  core(message: string): void;
}

export const HOT_SETTING_KEYS = ["watchlist"] as const;
export const RESTART_SETTING_KEYS = ["coreRoot", "uvPath", "provider", "replayPath"] as const;

export type SettingKey = (typeof HOT_SETTING_KEYS)[number] | (typeof RESTART_SETTING_KEYS)[number];

export const HOST_COMMANDS = {
  pause: "marketSentinel.pause",
  resume: "marketSentinel.resume",
  restartCore: "marketSentinel.restartCore",
  showOutput: "marketSentinel.showOutput",
} as const;
