import { formatAlertDiagnostic } from "../alerts/state";
import { ProtocolError } from "../ipc/errors";
import {
  ProcessManager,
  type DelayFn,
  type ProcessManagerOptions,
  type SpawnFn,
} from "../ipc/process";
import { mapHover, type HoverModel } from "../hover/model";
import type { AlertMessage, FeedbackType, WatchlistItem, WireMarketState } from "../protocol/types";
import {
  DEFAULT_ALERT_HOLD_MS,
  mapStatusBar,
  type StatusBarModel,
} from "../statusbar/map";
import { parseEnableHoverDetails, parseHostSettings } from "./config";
import {
  displaySymbol,
  parseStatusBarMaxSymbols,
  parseSymbolDisplay,
  parseSymbolNames,
} from "./display";
import type {
  ActualState,
  DesiredState,
  HostConfig,
  HostLogger,
  RawSettings,
  SettingKey,
} from "./types";
import { HOST_UI_SETTING_KEYS, HOT_SETTING_KEYS, RESTART_SETTING_KEYS } from "./types";
import { planAddSymbol, planRemoveSymbol } from "./watchlistEdit";

export const DEFAULT_BACKOFF_MS = [1_000, 3_000, 10_000] as const;
export const DEFAULT_MAX_RETRIES = 3;

const FEEDBACK_TYPES = new Set<FeedbackType>(["useful", "not_useful", "too_noisy", "too_late"]);
const MAX_FEEDBACK_TARGETS = 20;

const RESTART_HINT = "Market Sentinel core configuration changed; restart core to apply.";

export interface HostUiSnapshot {
  statusBar: StatusBarModel;
  hover: HoverModel;
}

export interface HostControllerOptions {
  readSettings: () => RawSettings;
  workspaceFolders: () => string[];
  logger: HostLogger;
  spawnFn?: SpawnFn;
  delay?: DelayFn;
  createManager?: (options: ProcessManagerOptions) => ProcessManager;
  backoffMs?: readonly number[];
  maxRetries?: number;
  helloTimeoutMs?: number;
  defaultTimeoutMs?: number;
  now?: () => number;
  alertHoldMs?: number;
  setTimeoutFn?: typeof setTimeout;
  clearTimeoutFn?: typeof clearTimeout;
  onUiSnapshot?: (snapshot: HostUiSnapshot) => void;
  onAlertEdge?: (message: AlertMessage) => void;
  persistWatchlist?: (items: WatchlistItem[]) => Promise<void>;
}

function defaultDelay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export class HostController {
  private readonly options: HostControllerOptions;
  private readonly backoffMs: readonly number[];
  private readonly maxRetries: number;
  private readonly createManager: (options: ProcessManagerOptions) => ProcessManager;
  private readonly delayFn: DelayFn;

  private desiredInternal: DesiredState = "RUNNING";
  private actualInternal: ActualState = "STOPPED";
  private manager: ProcessManager | undefined;
  private spawnConfig: Omit<HostConfig, "watchlist"> | undefined;
  private lastAcked: WatchlistItem[] = [];
  private retryCount = 0;
  private restartNeededInternal = false;
  private disposed = false;
  private restartInFlight = false;
  private lastErrorInternal: string | undefined;
  private coreVersionInternal: string | undefined;
  private managerGeneration = 0;
  private lastMarket: WireMarketState | undefined;
  private presentedFeedbackTargets: Array<{ id: string; label: string }> = [];
  private lastAlertAt: number | undefined;
  private unreadAlertCountInternal = 0;
  private alertHoldTimer: ReturnType<typeof setTimeout> | undefined;
  private presentationQueue: Promise<void> = Promise.resolve();

  constructor(options: HostControllerOptions) {
    this.options = options;
    this.backoffMs = options.backoffMs ?? DEFAULT_BACKOFF_MS;
    this.maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
    this.createManager = options.createManager ?? ((opts) => new ProcessManager(opts));
    this.delayFn = options.delay ?? defaultDelay;
  }

  get desiredState(): DesiredState {
    return this.desiredInternal;
  }

  get actualState(): ActualState {
    return this.actualInternal;
  }

  get restartNeeded(): boolean {
    return this.restartNeededInternal;
  }

  get lastError(): string | undefined {
    return this.lastErrorInternal;
  }

  get lastCoreVersion(): string | undefined {
    return this.coreVersionInternal;
  }

  get lastPid(): number | undefined {
    return this.manager?.lastPid;
  }

  get lastAcknowledgedWatchlist(): WatchlistItem[] {
    return this.lastAcked.map((item) => ({ ...item }));
  }

  get unreadAlertCount(): number {
    return this.unreadAlertCountInternal;
  }

  statusBarModel(): StatusBarModel {
    const settings = this.options.readSettings();
    return mapStatusBar({
      actual: this.actualInternal,
      desired: this.desiredInternal,
      market: this.lastMarket,
      lastAlertAt: this.lastAlertAt,
      now: (this.options.now ?? Date.now)(),
      alertHoldMs: this.options.alertHoldMs ?? DEFAULT_ALERT_HOLD_MS,
      lastError: this.lastErrorInternal,
      restartNeeded: this.restartNeededInternal,
      unreadAlertCount: this.unreadAlertCountInternal,
      symbolNames: parseSymbolNames(settings.symbolNames),
      symbolDisplay: parseSymbolDisplay(settings.symbolDisplay),
      maxSymbols: parseStatusBarMaxSymbols(settings.statusBarMaxSymbols),
    });
  }

  hoverModel(): HoverModel {
    const settings = this.options.readSettings();
    return mapHover({
      actual: this.actualInternal,
      market: this.lastMarket,
      enableHoverDetails: parseEnableHoverDetails(settings.enableHoverDetails),
      unreadAlertCount: this.unreadAlertCountInternal,
      symbolNames: parseSymbolNames(settings.symbolNames),
      symbolDisplay: parseSymbolDisplay(settings.symbolDisplay),
    });
  }

  uiSnapshot(): HostUiSnapshot {
    return { statusBar: this.statusBarModel(), hover: this.hoverModel() };
  }

  watchlistItems(): WatchlistItem[] {
    const parsed = parseHostSettings(this.options.readSettings(), this.options.workspaceFolders());
    if (parsed.ok) {
      return parsed.config.watchlist;
    }
    return this.lastAcked.map((item) => ({ ...item }));
  }

  watchlistChoices(): Array<{ label: string; symbol: string }> {
    const names = parseSymbolNames(this.options.readSettings().symbolNames);
    const mode = parseSymbolDisplay(this.options.readSettings().symbolDisplay);
    return this.watchlistItems().map((item) => ({
      symbol: item.symbol,
      label: displaySymbol(item.symbol, names, mode, "hover"),
    }));
  }

  async addWatchlistSymbol(raw: string): Promise<{ ok: true } | { ok: false; error: string }> {
    const planned = planAddSymbol(this.watchlistItems(), raw);
    if (!planned.ok) {
      this.options.logger.host(`addSymbol rejected: ${planned.error}`);
      return planned;
    }
    return this.commitWatchlist(planned.items);
  }

  async removeWatchlistSymbol(
    symbol: string,
  ): Promise<{ ok: true } | { ok: false; error: string }> {
    const planned = planRemoveSymbol(this.watchlistItems(), symbol);
    if (!planned.ok) {
      this.options.logger.host(`removeSymbol rejected: ${planned.error}`);
      return planned;
    }
    return this.commitWatchlist(planned.items);
  }

  private async commitWatchlist(
    items: WatchlistItem[],
  ): Promise<{ ok: true } | { ok: false; error: string }> {
    try {
      await this.options.persistWatchlist?.(items);
    } catch (error) {
      const message = this.errorMessage(error);
      this.options.logger.host(`watchlist persist failed: ${message}`);
      return { ok: false, error: message };
    }
    if (this.manager !== undefined && this.manager.connected) {
      try {
        await this.manager.setWatchlist(items);
        this.lastAcked = this.manager.acknowledgedWatchlist;
      } catch (error) {
        const message = this.errorMessage(error);
        this.options.logger.host(`watchlist update rejected: ${message}`);
        return { ok: false, error: message };
      }
    }
    this.emitUi();
    return { ok: true };
  }

  resetAlertBadge(): void {
    this.unreadAlertCountInternal = 0;
    this.reportHostInteraction({ action: "alert_badge_reset" });
    this.emitUi();
  }

  signalFeedbackTargets(): Array<{ id: string; label: string }> {
    const labels = new Map<string, string>();
    for (const item of this.presentedFeedbackTargets) {
      labels.set(item.id, item.label);
    }
    for (const symbol of this.lastMarket?.symbols ?? []) {
      for (const signal of symbol.active_signals) {
        labels.set(signal.id, `${symbol.symbol} ${signal.title}`);
      }
    }
    return [...labels.entries()].map(([id, label]) => ({ id, label }));
  }

  async submitSignalFeedback(signalId: string, feedbackType: FeedbackType): Promise<void> {
    if (signalId.trim() === "" || !FEEDBACK_TYPES.has(feedbackType)) {
      this.options.logger.host("submitSignalFeedback ignored invalid payload");
      return;
    }
    const ipc = this.manager?.ipc;
    if (ipc === undefined) {
      this.options.logger.host("submitSignalFeedback skipped: core not connected");
      return;
    }
    if (!this.signalFeedbackTargets().some((item) => item.id === signalId)) {
      this.options.logger.host("submitSignalFeedback skipped: stale signal_id");
      return;
    }
    const created_timestamp = (this.options.now ?? Date.now)() / 1000;
    try {
      await ipc.request({
        type: "user_feedback",
        signal_id: signalId,
        feedback_type: feedbackType,
        created_timestamp,
      });
    } catch (error) {
      this.options.logger.host(`user_feedback failed: ${this.errorMessage(error)}`);
    }
  }

  async start(): Promise<void> {
    this.desiredInternal = "RUNNING";
    try {
      await this.connectFromSettings();
    } catch (error) {
      this.failDisconnected(error);
    }
  }

  async shutdown(): Promise<void> {
    this.disposed = true;
    this.restartInFlight = false;
    this.clearAlertHold();
    await this.presentationQueue.catch(() => undefined);
    if (this.actualInternal === "STOPPED" && this.manager === undefined) {
      this.emitUi();
      return;
    }
    this.setActual("STOPPING");
    await this.disposeManager();
    this.setActual("STOPPED");
  }

  async pause(): Promise<void> {
    this.desiredInternal = "PAUSED";
    if (this.actualInternal === "DISCONNECTED" || this.actualInternal === "STOPPED") {
      this.options.logger.host("pause requested while disconnected; core will stay stopped");
      this.emitUi();
      return;
    }
    if (this.manager === undefined || !this.manager.connected) {
      this.setActual("DISCONNECTED");
      return;
    }
    try {
      await this.manager.pause();
      this.setActual("PAUSED");
    } catch (error) {
      this.options.logger.host(`pause failed: ${this.errorMessage(error)}`);
      this.emitUi();
    }
  }

  async resume(): Promise<void> {
    this.desiredInternal = "RUNNING";
    this.retryCount = 0;
    if (this.actualInternal === "PAUSED" && this.manager !== undefined && this.manager.connected) {
      try {
        await this.manager.resume();
        this.setActual("RUNNING");
        return;
      } catch (error) {
        this.options.logger.host(`resume failed: ${this.errorMessage(error)}`);
        this.setActual("DISCONNECTED");
      }
    }
    try {
      await this.connectFromSettings();
    } catch (error) {
      this.failDisconnected(error);
    }
  }

  async restartCore(): Promise<void> {
    this.retryCount = 0;
    await this.disposeManager();
    this.restartNeededInternal = false;
    if (this.desiredInternal === "PAUSED") {
      this.setActual("STOPPED");
      this.options.logger.host("restartCore skipped spawn because desiredState is PAUSED");
      return;
    }
    try {
      await this.connectFromSettings();
    } catch (error) {
      this.failDisconnected(error);
    }
  }

  async onConfigurationChanged(keys: readonly string[]): Promise<void> {
    const relevant = keys.filter((key) => this.isSettingKey(key));
    if (relevant.length === 0) {
      return;
    }
    if (relevant.some((key) => (RESTART_SETTING_KEYS as readonly string[]).includes(key))) {
      this.restartNeededInternal = true;
      this.options.logger.host(RESTART_HINT);
      this.emitUi();
    }
    if (relevant.includes("watchlist")) {
      await this.applyWatchlistHotUpdate();
    }
    if (relevant.some((key) => (HOST_UI_SETTING_KEYS as readonly string[]).includes(key))) {
      this.emitUi();
    }
  }

  private isSettingKey(key: string): key is SettingKey {
    return (
      (HOT_SETTING_KEYS as readonly string[]).includes(key) ||
      (HOST_UI_SETTING_KEYS as readonly string[]).includes(key) ||
      (RESTART_SETTING_KEYS as readonly string[]).includes(key)
    );
  }

  private async applyWatchlistHotUpdate(): Promise<void> {
    const parsed = parseHostSettings(this.options.readSettings(), this.options.workspaceFolders());
    if (!parsed.ok) {
      this.options.logger.host(`watchlist setting ignored: ${parsed.error}`);
      return;
    }
    if (this.manager === undefined || !this.manager.connected) {
      return;
    }
    try {
      await this.manager.setWatchlist(parsed.config.watchlist);
      this.lastAcked = this.manager.acknowledgedWatchlist;
    } catch (error) {
      this.options.logger.host(`watchlist update rejected: ${this.errorMessage(error)}`);
    }
  }

  private async connectFromSettings(): Promise<void> {
    const parsed = parseHostSettings(this.options.readSettings(), this.options.workspaceFolders());
    if (!parsed.ok) {
      throw new Error(parsed.error);
    }
    this.spawnConfig = {
      coreRoot: parsed.config.coreRoot,
      uvPath: parsed.config.uvPath,
      provider: parsed.config.provider,
      replayPath: parsed.config.replayPath,
      intelligence: parsed.config.intelligence,
    };
    await this.spawnAndStart(parsed.config.watchlist);
  }

  private async connectWithRuntimeWatchlist(): Promise<void> {
    if (this.spawnConfig === undefined) {
      await this.connectFromSettings();
      return;
    }
    const parsed = parseHostSettings(this.options.readSettings(), this.options.workspaceFolders());
    const watchlist = parsed.ok ? parsed.config.watchlist : this.lastAcked;
    await this.spawnAndStart(watchlist);
  }

  private async spawnAndStart(watchlist: WatchlistItem[]): Promise<void> {
    if (this.spawnConfig === undefined) {
      throw new Error("spawn configuration is missing");
    }
    await this.disposeManager();
    this.setActual("STARTING");
    const generation = ++this.managerGeneration;
    const spawnSnapshot = this.spawnConfig;
    const manager = this.createManager({
      coreRoot: spawnSnapshot.coreRoot,
      uvPath: spawnSnapshot.uvPath,
      provider: spawnSnapshot.provider,
      replayPath: spawnSnapshot.replayPath,
      intelligence: spawnSnapshot.intelligence,
      watchlist,
      spawnFn: this.options.spawnFn,
      helloTimeoutMs: this.options.helloTimeoutMs,
      defaultTimeoutMs: this.options.defaultTimeoutMs,
      onStderr: (chunk) => this.options.logger.core(chunk),
      onProtocolError: (error) => {
        this.options.logger.host(`protocol error ${error.code}: ${error.message}`);
      },
      onReady: (coreVersion) => {
        this.coreVersionInternal = coreVersion;
        this.options.logger.host(
          `core ready core_version=${coreVersion} (diagnostics only; wire compatibility is protocol_version)`,
        );
      },
      onDisconnected: (reason) => {
        if (generation !== this.managerGeneration) {
          return;
        }
        this.options.logger.host(`core disconnected: ${reason}`);
        void this.handleUnexpectedDisconnect();
      },
      onState: (message) => {
        if (generation !== this.managerGeneration) {
          return;
        }
        this.lastMarket = message.state;
        this.emitUi();
      },
      onAlert: (message) => {
        if (generation !== this.managerGeneration) {
          return;
        }
        this.enqueueAlert(message);
      },
    });
    this.manager = manager;
    await manager.start(watchlist);
    this.lastAcked = manager.acknowledgedWatchlist;
    try {
      const snapshot = await manager.getState();
      this.lastMarket = snapshot.state;
    } catch (error) {
      this.options.logger.host(`get_state after start failed: ${this.errorMessage(error)}`);
    }
    this.setActual("RUNNING");
    this.retryCount = 0;
    this.lastErrorInternal = undefined;
  }

  private async handleUnexpectedDisconnect(): Promise<void> {
    this.manager = undefined;
    this.clearExecutionFeedbackTargets();
    this.lastAlertAt = undefined;
    this.clearAlertHold();
    this.setActual("DISCONNECTED");
    if (this.disposed || this.desiredInternal !== "RUNNING") {
      this.options.logger.host("core exited while desiredState is not RUNNING; not auto-restarting");
      return;
    }
    if (this.restartInFlight) {
      return;
    }
    this.restartInFlight = true;
    try {
      while (!this.disposed && this.desiredInternal === "RUNNING") {
        if (this.retryCount >= this.maxRetries) {
          this.options.logger.host("auto-restart gave up after 3 attempts");
          this.setActual("DISCONNECTED");
          return;
        }
        const wait = this.backoffMs[Math.min(this.retryCount, this.backoffMs.length - 1)] ?? 0;
        this.retryCount += 1;
        this.options.logger.host(`restart attempt ${this.retryCount} after ${wait}ms`);
        await this.delayFn(wait);
        if (this.disposed || this.desiredInternal !== "RUNNING") {
          return;
        }
        try {
          await this.connectWithRuntimeWatchlist();
          return;
        } catch (error) {
          this.failDisconnected(error);
        }
      }
    } finally {
      this.restartInFlight = false;
    }
  }

  private async disposeManager(): Promise<void> {
    this.managerGeneration += 1;
    this.clearExecutionFeedbackTargets();
    await this.presentationQueue.catch(() => undefined);
    this.lastMarket = undefined;
    const manager = this.manager;
    this.manager = undefined;
    if (manager !== undefined) {
      await manager.shutdown();
    }
  }

  private failDisconnected(error: unknown): void {
    const message = this.errorMessage(error);
    this.lastErrorInternal = message;
    this.clearExecutionFeedbackTargets();
    this.lastMarket = undefined;
    this.lastAlertAt = undefined;
    this.clearAlertHold();
    this.setActual("DISCONNECTED");
    this.options.logger.host(message);
    if (error instanceof ProtocolError) {
      this.options.logger.host(`core error code=${error.code} request_id=${error.requestId ?? ""}`);
    }
  }

  private enqueueAlert(message: AlertMessage): void {
    this.unreadAlertCountInternal += message.candidates.length;
    for (const candidate of message.candidates) {
      this.options.logger.host(formatAlertDiagnostic(candidate));
      this.rememberFeedbackTarget(candidate.id, `${candidate.symbol} ${candidate.title}`);
    }
    this.lastAlertAt = (this.options.now ?? Date.now)();
    this.clearAlertHold();
    const hold = this.options.alertHoldMs ?? DEFAULT_ALERT_HOLD_MS;
    const setTimeoutFn = this.options.setTimeoutFn ?? setTimeout;
    this.alertHoldTimer = setTimeoutFn(() => {
      this.alertHoldTimer = undefined;
      this.emitUi();
    }, hold);
    this.options.onAlertEdge?.(message);
    this.emitUi();
    this.presentationQueue = this.presentationQueue.then(() => this.flushPresented(message));
  }

  private async flushPresented(message: AlertMessage): Promise<void> {
    const ipc = this.manager?.ipc;
    if (ipc === undefined) {
      return;
    }
    for (const candidate of message.candidates) {
      const created_timestamp = (this.options.now ?? Date.now)() / 1000;
      try {
        await ipc.request({
          type: "host_interaction",
          action: "alert_presented",
          signal_id: candidate.id,
          created_timestamp,
        });
      } catch (error) {
        this.options.logger.host(
          `host_interaction alert_presented failed: ${this.errorMessage(error)}`,
        );
      }
    }
  }

  private clearExecutionFeedbackTargets(): void {
    this.presentedFeedbackTargets = [];
  }

  private rememberFeedbackTarget(id: string, label: string): void {
    this.presentedFeedbackTargets = [
      ...this.presentedFeedbackTargets.filter((item) => item.id !== id),
      { id, label },
    ].slice(-MAX_FEEDBACK_TARGETS);
  }

  private reportHostInteraction(input: {
    action: "alert_presented" | "alert_badge_reset";
    signal_id?: string;
  }): void {
    const ipc = this.manager?.ipc;
    if (ipc === undefined) {
      return;
    }
    const created_timestamp = (this.options.now ?? Date.now)() / 1000;
    const body =
      input.action === "alert_presented"
        ? {
            type: "host_interaction" as const,
            action: input.action,
            signal_id: input.signal_id,
            created_timestamp,
          }
        : {
            type: "host_interaction" as const,
            action: input.action,
            created_timestamp,
          };
    void ipc.request(body).catch((error: unknown) => {
      this.options.logger.host(
        `host_interaction ${input.action} failed: ${this.errorMessage(error)}`,
      );
    });
  }

  private clearAlertHold(): void {
    if (this.alertHoldTimer !== undefined) {
      const clearTimeoutFn = this.options.clearTimeoutFn ?? clearTimeout;
      clearTimeoutFn(this.alertHoldTimer);
      this.alertHoldTimer = undefined;
    }
  }

  private setActual(state: ActualState): void {
    this.actualInternal = state;
    this.emitUi();
  }

  private emitUi(): void {
    this.options.onUiSnapshot?.(this.uiSnapshot());
  }

  private errorMessage(error: unknown): string {
    if (error instanceof Error) {
      const extra =
        "code" in error && typeof (error as { code?: unknown }).code === "string"
          ? ` code=${(error as { code: string }).code}`
          : "";
      if (/ENOENT/i.test(error.message) || extra.includes("ENOENT")) {
        const uvPath = this.spawnConfig?.uvPath ?? this.options.readSettings().uvPath ?? "uv";
        const coreRoot = this.spawnConfig?.coreRoot ?? "";
        return `uv executable not found (uvPath=${uvPath}, coreRoot=${coreRoot}): ${error.message}`;
      }
      return error.message;
    }
    return String(error);
  }
}
