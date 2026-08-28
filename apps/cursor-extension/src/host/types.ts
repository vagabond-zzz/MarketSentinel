import type { WatchlistItem } from "../protocol/types";

export type DesiredState = "RUNNING" | "PAUSED";

export type ActualState =
  | "STARTING"
  | "RUNNING"
  | "PAUSED"
  | "DISCONNECTED"
  | "STOPPING"
  | "STOPPED";

export type ProviderName = "fake" | "replay" | "longbridge";

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
  enableHoverDetails?: unknown;
  alertToast?: unknown;
}

export interface HostLogger {
  host(message: string): void;
  core(message: string): void;
}

export const HOT_SETTING_KEYS = ["watchlist"] as const;
export const HOST_UI_SETTING_KEYS = ["enableHoverDetails", "alertToast"] as const;
export const RESTART_SETTING_KEYS = ["coreRoot", "uvPath", "provider", "replayPath"] as const;

export type SettingKey =
  | (typeof HOT_SETTING_KEYS)[number]
  | (typeof HOST_UI_SETTING_KEYS)[number]
  | (typeof RESTART_SETTING_KEYS)[number];

export const HOST_COMMANDS = {
  pause: "marketSentinel.pause",
  resume: "marketSentinel.resume",
  restartCore: "marketSentinel.restartCore",
  showOutput: "marketSentinel.showOutput",
  resetAlertBadge: "marketSentinel.resetAlertBadge",
  submitSignalFeedback: "marketSentinel.submitSignalFeedback",
} as const;

export const EXTENSION_ID = "market-sentinel-local.market-sentinel";
