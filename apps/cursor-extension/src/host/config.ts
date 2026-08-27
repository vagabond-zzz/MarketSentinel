import { isRecord } from "../protocol/guards";
import type { WatchlistItem } from "../protocol/types";
import type { HostConfig, ProviderName, RawSettings } from "./types";

export class HostConfigError extends Error {
  readonly code = "configuration";

  constructor(message: string) {
    super(message);
    this.name = "HostConfigError";
  }
}

export type ConfigParseResult = { ok: true; config: HostConfig } | { ok: false; error: string };

export function resolveCoreRoot(
  explicit: string | undefined,
  workspaceFolders: readonly string[],
): string {
  const trimmed = explicit?.trim() ?? "";
  if (trimmed.length > 0) {
    return trimmed;
  }
  if (workspaceFolders.length === 1) {
    const folder = workspaceFolders[0];
    if (folder !== undefined && folder.length > 0) {
      return folder;
    }
  }
  if (workspaceFolders.length === 0) {
    throw new HostConfigError(
      "marketSentinel.coreRoot is required when no workspace folder is open",
    );
  }
  throw new HostConfigError(
    "marketSentinel.coreRoot is required for a multi-root workspace; refusing to guess a folder",
  );
}

export function parseWatchlist(raw: unknown): WatchlistItem[] {
  if (raw === undefined) {
    return [];
  }
  if (!Array.isArray(raw)) {
    throw new HostConfigError("marketSentinel.watchlist must be an array");
  }
  const items: WatchlistItem[] = [];
  for (const [index, entry] of raw.entries()) {
    if (typeof entry === "string") {
      if (entry.trim().length === 0) {
        throw new HostConfigError(`watchlist[${index}] symbol must be a non-empty string`);
      }
      items.push({ symbol: entry, enabled: true });
      continue;
    }
    if (!isRecord(entry) || typeof entry.symbol !== "string" || entry.symbol.trim().length === 0) {
      throw new HostConfigError(`watchlist[${index}] needs a non-empty symbol`);
    }
    const enabled = entry.enabled === undefined ? true : entry.enabled;
    if (typeof enabled !== "boolean") {
      throw new HostConfigError(`watchlist[${index}].enabled must be a boolean`);
    }
    items.push({ symbol: entry.symbol, enabled });
  }
  return items;
}

export function parseProvider(raw: unknown): ProviderName {
  if (raw === undefined || raw === "") {
    return "fake";
  }
  if (raw === "fake" || raw === "replay") {
    return raw;
  }
  throw new HostConfigError('marketSentinel.provider must be "fake" or "replay"');
}

export function parseEnableHoverDetails(raw: unknown): boolean {
  return raw !== false;
}

export function parseHostSettings(
  raw: RawSettings,
  workspaceFolders: readonly string[],
): ConfigParseResult {
  try {
    const coreRoot = resolveCoreRoot(raw.coreRoot, workspaceFolders);
    const uvPath = (raw.uvPath ?? "uv").trim();
    if (uvPath.length === 0) {
      throw new HostConfigError("marketSentinel.uvPath must be a non-empty executable path");
    }
    const provider = parseProvider(raw.provider);
    const replayTrimmed = raw.replayPath?.trim() ?? "";
    const replayPath = replayTrimmed.length > 0 ? replayTrimmed : undefined;
    if (provider === "replay" && replayPath === undefined) {
      throw new HostConfigError("marketSentinel.replayPath is required when provider is replay");
    }
    const watchlist = parseWatchlist(raw.watchlist);
    return {
      ok: true,
      config: {
        coreRoot,
        uvPath,
        provider,
        watchlist,
        ...(replayPath !== undefined ? { replayPath } : {}),
      },
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, error: message };
  }
}
