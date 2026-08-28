import { spawn, type ChildProcess, type SpawnOptions } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

import { IpcClient } from "./client";
import { IpcDisconnectedError, IpcTimeoutError, ProtocolError } from "./errors";
import type { AckMessage, AlertMessage, StateMessage, WatchlistItem } from "../protocol/types";

export type ProcessPhase = "STOPPED" | "STARTING" | "RUNNING" | "STOPPING" | "DISCONNECTED";

export type SpawnFn = (
  command: string,
  args: readonly string[],
  options: SpawnOptions,
) => ChildProcess;

export type DelayFn = (ms: number) => Promise<void>;

export interface ProcessManagerOptions {
  uvPath?: string;
  coreRoot: string;
  provider?: "fake" | "replay" | "longbridge";
  replayPath?: string;
  watchlist?: WatchlistItem[];
  spawnFn?: SpawnFn;
  delay?: DelayFn;
  shutdownGraceMs?: number;
  helloTimeoutMs?: number;
  defaultTimeoutMs?: number;
  requestId?: () => string;
  onStderr?: (chunk: string) => void;
  onState?: (message: StateMessage) => void;
  onAlert?: (message: AlertMessage) => void;
  onProtocolError?: (error: ProtocolError) => void;
  onReady?: (coreVersion: string) => void;
  onDisconnected?: (reason: string) => void;
}

function extensionVersion(): string {
  const pkgPath = path.join(__dirname, "..", "..", "package.json");
  const parsed = JSON.parse(readFileSync(pkgPath, "utf8")) as { version?: string };
  if (typeof parsed.version !== "string" || parsed.version.length === 0) {
    throw new Error("extension package.json is missing version");
  }
  return parsed.version;
}

function defaultDelay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function waitForExit(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    child.once("exit", () => resolve());
  });
}

export class ProcessManager {
  private readonly options: ProcessManagerOptions;
  private phaseInternal: ProcessPhase = "STOPPED";
  private child: ChildProcess | undefined;
  private client: IpcClient | undefined;
  private ackedWatchlist: WatchlistItem[] = [];
  private desiredWatchlist: WatchlistItem[] = [];
  private stdoutHandler: ((chunk: string | Buffer) => void) | undefined;
  private stderrHandler: ((chunk: string | Buffer) => void) | undefined;
  private exitHandler: ((code: number | null, signal: NodeJS.Signals | null) => void) | undefined;
  private errorHandler: ((error: Error) => void) | undefined;
  private stopping = false;
  private live = false;
  private disconnectSent = false;
  private lastPidInternal: number | undefined;

  constructor(options: ProcessManagerOptions) {
    this.options = options;
    this.desiredWatchlist = options.watchlist ?? [];
  }

  get phase(): ProcessPhase {
    return this.phaseInternal;
  }

  get ipc(): IpcClient | undefined {
    return this.client;
  }

  get lastPid(): number | undefined {
    return this.lastPidInternal;
  }

  get acknowledgedWatchlist(): WatchlistItem[] {
    return this.ackedWatchlist.map((item) => ({ ...item }));
  }

  get connected(): boolean {
    return this.client !== undefined;
  }

  daemonArgs(): { command: string; args: string[] } {
    // Option A: Host never passes `--extra live`. SDK install is a manual `uv sync --extra live`.
    const command = this.options.uvPath ?? "uv";
    const args = [
      "run",
      "--directory",
      this.options.coreRoot,
      "market-sentinel",
      "--provider",
      this.options.provider ?? "fake",
    ];
    if (this.options.provider === "replay") {
      if (this.options.replayPath === undefined) {
        throw new Error("--replay path is required for replay provider");
      }
      args.push("--replay", this.options.replayPath);
    }
    args.push("daemon");
    return { command, args };
  }

  async start(watchlist?: WatchlistItem[]): Promise<void> {
    if (this.phaseInternal === "RUNNING" || this.phaseInternal === "STARTING") {
      throw new Error(`cannot start from ${this.phaseInternal}`);
    }
    if (watchlist !== undefined) {
      this.desiredWatchlist = watchlist;
    }
    await this.spawnAndHandshake(this.desiredWatchlist);
  }

  async setWatchlist(items: WatchlistItem[]): Promise<AckMessage> {
    if (this.client === undefined || this.phaseInternal !== "RUNNING") {
      throw new IpcDisconnectedError("daemon is not running");
    }
    const previous = this.ackedWatchlist;
    try {
      const response = await this.client.request({ type: "set_watchlist", items });
      if (response.type !== "ack") {
        throw new ProtocolError("unexpected_type", `expected ack, got ${response.type}`);
      }
      this.ackedWatchlist = items.map((item) => ({ ...item }));
      this.desiredWatchlist = this.ackedWatchlist;
      return response;
    } catch (error) {
      this.ackedWatchlist = previous;
      throw error;
    }
  }

  async pause(): Promise<AckMessage> {
    return this.requireAck("pause");
  }

  async resume(): Promise<AckMessage> {
    return this.requireAck("resume");
  }

  async getState(): Promise<StateMessage> {
    if (this.client === undefined) {
      throw new IpcDisconnectedError("daemon is not running");
    }
    const response = await this.client.request({ type: "get_state" });
    if (response.type !== "state") {
      throw new ProtocolError("unexpected_type", `expected state, got ${response.type}`);
    }
    return response;
  }

  async shutdown(): Promise<void> {
    if (this.child === undefined && this.client === undefined) {
      this.phaseInternal = "STOPPED";
      return;
    }
    this.stopping = true;
    this.phaseInternal = "STOPPING";
    const grace = this.options.shutdownGraceMs ?? 2_000;
    try {
      if (this.client !== undefined && this.child !== undefined && this.child.exitCode === null) {
        try {
          const timeout = (this.options.delay ?? defaultDelay)(grace).then(() => {
            throw new IpcTimeoutError("shutdown", grace);
          });
          await Promise.race([this.client.request({ type: "shutdown" }), timeout]);
        } catch {
          this.child.kill();
        }
        await Promise.race([
          waitForExit(this.child),
          (this.options.delay ?? defaultDelay)(grace).then(() => {
            this.child?.kill();
          }),
        ]);
      }
    } finally {
      this.cleanup({ rejectPending: true, reason: "shutdown" });
      this.phaseInternal = "STOPPED";
      this.stopping = false;
    }
  }

  async restartOnce(): Promise<void> {
    const watchlist = this.ackedWatchlist;
    this.stopping = true;
    this.phaseInternal = "STOPPING";
    if (this.child !== undefined && this.child.exitCode === null) {
      this.child.kill();
      await waitForExit(this.child);
    }
    this.cleanup({ rejectPending: true, reason: "restart" });
    this.stopping = false;
    await this.spawnAndHandshake(watchlist);
  }

  private async requireAck(type: "pause" | "resume"): Promise<AckMessage> {
    if (this.client === undefined) {
      throw new IpcDisconnectedError("daemon is not running");
    }
    const response = await this.client.request({ type });
    if (response.type !== "ack") {
      throw new ProtocolError("unexpected_type", `expected ack, got ${response.type}`);
    }
    return response;
  }

  private async spawnAndHandshake(watchlist: WatchlistItem[]): Promise<void> {
    this.live = false;
    this.disconnectSent = false;
    this.phaseInternal = "STARTING";
    const { command, args } = this.daemonArgs();
    const spawnFn = this.options.spawnFn ?? spawn;
    const child = spawnFn(command, args, {
      stdio: ["pipe", "pipe", "pipe"],
      shell: false,
      windowsHide: true,
    });
    this.child = child;
    this.lastPidInternal = child.pid;
    const { stdin, stdout, stderr } = child;
    if (stdin === null || stdout === null || stderr === null) {
      return this.failStart(new Error("child stdio pipes are missing"));
    }
    const client = new IpcClient({
      write: (line) => {
        stdin.write(line);
      },
      helloTimeoutMs: this.options.helloTimeoutMs,
      defaultTimeoutMs: this.options.defaultTimeoutMs,
      requestId: this.options.requestId,
    });
    this.client = client;
    if (this.options.onState !== undefined) {
      client.onState(this.options.onState);
    }
    if (this.options.onAlert !== undefined) {
      client.onAlert(this.options.onAlert);
    }
    if (this.options.onProtocolError !== undefined) {
      client.onProtocolError(this.options.onProtocolError);
    }
    this.attachChild(child, client);
    try {
      const ready = await client.request({
        type: "hello",
        host: "cursor-extension",
        host_version: extensionVersion(),
      });
      if (ready.type !== "ready") {
        throw new ProtocolError("unexpected_type", `expected ready, got ${ready.type}`);
      }
      this.options.onReady?.(ready.core_version);
      const ack = await client.request({ type: "set_watchlist", items: watchlist });
      if (ack.type !== "ack") {
        throw new ProtocolError("unexpected_type", `expected ack, got ${ack.type}`);
      }
      this.ackedWatchlist = watchlist.map((item) => ({ ...item }));
      const started = await client.request({ type: "start" });
      if (started.type !== "ack") {
        throw new ProtocolError("unexpected_type", `expected ack, got ${started.type}`);
      }
      this.live = true;
      this.phaseInternal = "RUNNING";
    } catch (error) {
      return this.failStart(error);
    }
  }

  private attachChild(child: ChildProcess, client: IpcClient): void {
    this.stdoutHandler = (chunk: string | Buffer) => {
      client.feed(chunk);
    };
    this.stderrHandler = (chunk: string | Buffer) => {
      const text = typeof chunk === "string" ? chunk : chunk.toString("utf8");
      this.options.onStderr?.(text);
    };
    this.exitHandler = () => {
      if (this.stopping) {
        return;
      }
      this.phaseInternal = "DISCONNECTED";
      this.cleanup({ rejectPending: true, reason: "child exit" });
    };
    this.errorHandler = (error: Error) => {
      if (this.stopping) {
        return;
      }
      this.phaseInternal = "DISCONNECTED";
      this.cleanup({ rejectPending: true, reason: error.message });
    };
    child.stdout?.on("data", this.stdoutHandler);
    child.stderr?.on("data", this.stderrHandler);
    child.stdout?.on("close", this.exitHandler);
    child.on("exit", this.exitHandler);
    child.on("error", this.errorHandler);
  }

  private failStart(error: unknown): never {
    this.stopping = true;
    if (this.child !== undefined && this.child.exitCode === null) {
      this.child.kill();
    }
    this.cleanup({ rejectPending: true, reason: "start failed" });
    this.phaseInternal = "DISCONNECTED";
    this.stopping = false;
    if (error instanceof Error) {
      throw error;
    }
    throw new Error(String(error));
  }

  private cleanup(opts: { rejectPending: boolean; reason: string }): void {
    const notifyDisconnect = this.live && !this.stopping && !this.disconnectSent;
    this.live = false;
    if (notifyDisconnect) {
      this.disconnectSent = true;
    }
    const child = this.child;
    const client = this.client;
    if (child !== undefined) {
      if (this.stdoutHandler !== undefined) {
        child.stdout?.off("data", this.stdoutHandler);
      }
      if (this.stderrHandler !== undefined) {
        child.stderr?.off("data", this.stderrHandler);
      }
      if (this.exitHandler !== undefined) {
        child.stdout?.off("close", this.exitHandler);
        child.off("exit", this.exitHandler);
      }
      if (this.errorHandler !== undefined) {
        child.off("error", this.errorHandler);
      }
    }
    this.stdoutHandler = undefined;
    this.stderrHandler = undefined;
    this.exitHandler = undefined;
    this.errorHandler = undefined;
    this.child = undefined;
    this.client = undefined;
    if (client !== undefined) {
      if (opts.rejectPending) {
        client.notifyClosed(opts.reason);
      }
      client.dispose();
    }
    if (notifyDisconnect) {
      this.options.onDisconnected?.(opts.reason);
    }
  }
}
