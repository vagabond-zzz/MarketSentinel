import { parseCoreMessage, peekRequestId } from "../protocol/guards";
import {
  EXPECTED_RESPONSE,
  PROTOCOL_VERSION,
  type AlertMessage,
  type CoreMessage,
  type HostCommandBody,
  type RequestSuccessMessage,
  type StateMessage,
} from "../protocol/types";
import { IpcDisconnectedError, IpcTimeoutError, ProtocolError } from "./errors";
import { JsonlDecoder } from "./jsonl";

export interface DisposableLike {
  dispose(): void;
}

export interface IpcClientOptions {
  write: (line: string) => void;
  helloTimeoutMs?: number;
  defaultTimeoutMs?: number;
  requestId?: () => string;
  setTimeoutFn?: typeof setTimeout;
  clearTimeoutFn?: typeof clearTimeout;
}

interface PendingRequest {
  expectedType: RequestSuccessMessage["type"];
  resolve: (message: RequestSuccessMessage) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

const HELLO_TIMEOUT_MS = 10_000;
const DEFAULT_TIMEOUT_MS = 5_000;

export class IpcClient {
  private readonly writeLine: (line: string) => void;
  private readonly helloTimeoutMs: number;
  private readonly defaultTimeoutMs: number;
  private readonly nextId: () => string;
  private readonly setTimeoutFn: typeof setTimeout;
  private readonly clearTimeoutFn: typeof clearTimeout;
  private readonly decoder = new JsonlDecoder();
  private readonly pending = new Map<string, PendingRequest>();
  private readonly stateHandlers = new Set<(message: StateMessage) => void>();
  private readonly alertHandlers = new Set<(message: AlertMessage) => void>();
  private readonly errorHandlers = new Set<(error: ProtocolError) => void>();
  private seq = 0;
  private closed = false;

  constructor(options: IpcClientOptions) {
    this.writeLine = options.write;
    this.helloTimeoutMs = options.helloTimeoutMs ?? HELLO_TIMEOUT_MS;
    this.defaultTimeoutMs = options.defaultTimeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.nextId = options.requestId ?? (() => `r${++this.seq}`);
    this.setTimeoutFn = options.setTimeoutFn ?? setTimeout;
    this.clearTimeoutFn = options.clearTimeoutFn ?? clearTimeout;
  }

  get pendingCount(): number {
    return this.pending.size;
  }

  feed(chunk: string | Buffer): void {
    for (const line of this.decoder.push(chunk)) {
      this.dispatchLine(line);
    }
  }

  notifyClosed(reason = "stdio closed"): void {
    this.rejectAll(new IpcDisconnectedError(reason));
    this.closed = true;
  }

  request(body: HostCommandBody): Promise<RequestSuccessMessage> {
    if (this.closed) {
      return Promise.reject(new IpcDisconnectedError());
    }
    const request_id = this.nextId();
    const timeoutMs = body.type === "hello" ? this.helloTimeoutMs : this.defaultTimeoutMs;
    const payload = {
      protocol_version: PROTOCOL_VERSION,
      request_id,
      ...body,
    };
    const expectedType = EXPECTED_RESPONSE[body.type];
    const promise = new Promise<RequestSuccessMessage>((resolve, reject) => {
      const timer = this.setTimeoutFn(() => {
        this.pending.delete(request_id);
        reject(new IpcTimeoutError(request_id, timeoutMs));
      }, timeoutMs);
      this.pending.set(request_id, { expectedType, resolve, reject, timer });
    });
    this.writeLine(`${JSON.stringify(payload)}\n`);
    return promise;
  }

  onState(handler: (message: StateMessage) => void): DisposableLike {
    this.stateHandlers.add(handler);
    return { dispose: () => this.stateHandlers.delete(handler) };
  }

  onAlert(handler: (message: AlertMessage) => void): DisposableLike {
    this.alertHandlers.add(handler);
    return { dispose: () => this.alertHandlers.delete(handler) };
  }

  onProtocolError(handler: (error: ProtocolError) => void): DisposableLike {
    this.errorHandlers.add(handler);
    return { dispose: () => this.errorHandlers.delete(handler) };
  }

  dispose(): void {
    this.rejectAll(new IpcDisconnectedError("client disposed"));
    this.closed = true;
    this.stateHandlers.clear();
    this.alertHandlers.clear();
    this.errorHandlers.clear();
  }

  private dispatchLine(line: string): void {
    let raw: unknown;
    try {
      raw = JSON.parse(line) as unknown;
    } catch {
      this.emitProtocolError(new ProtocolError("invalid_json", "line is not valid JSON"));
      return;
    }
    const parsed = parseCoreMessage(raw);
    if (!parsed.ok) {
      const requestId = parsed.requestId ?? peekRequestId(raw);
      const error = new ProtocolError("malformed_response", parsed.error, requestId);
      if (requestId !== undefined && this.pending.has(requestId)) {
        this.rejectPending(requestId, error);
        return;
      }
      this.emitProtocolError(error);
      return;
    }
    this.dispatchMessage(parsed.message);
  }

  private dispatchMessage(message: CoreMessage): void {
    if (message.type === "alert") {
      for (const handler of this.alertHandlers) {
        handler(message);
      }
      return;
    }
    if (message.type === "state" && message.request_id === undefined) {
      for (const handler of this.stateHandlers) {
        handler(message);
      }
      return;
    }
    const requestId = "request_id" in message ? message.request_id : undefined;
    if (requestId !== undefined && this.pending.has(requestId)) {
      if (message.type === "error") {
        this.rejectPending(
          requestId,
          new ProtocolError(message.code, message.message, requestId),
        );
        return;
      }
      const pending = this.pending.get(requestId);
      if (pending === undefined) {
        return;
      }
      if (message.type !== pending.expectedType) {
        this.rejectPending(
          requestId,
          new ProtocolError(
            "unexpected_type",
            `expected ${pending.expectedType}, got ${message.type}`,
            requestId,
          ),
        );
        return;
      }
      this.clearPending(requestId);
      pending.resolve(message);
      return;
    }
    if (message.type === "error") {
      this.emitProtocolError(
        new ProtocolError(message.code, message.message, message.request_id),
      );
      return;
    }
    this.emitProtocolError(
      new ProtocolError(
        "unknown_request_id",
        `no pending request for ${requestId ?? "missing id"}`,
        requestId,
      ),
    );
  }

  private rejectPending(requestId: string, error: Error): void {
    const pending = this.pending.get(requestId);
    if (pending === undefined) {
      return;
    }
    this.clearPending(requestId);
    pending.reject(error);
  }

  private clearPending(requestId: string): void {
    const pending = this.pending.get(requestId);
    if (pending === undefined) {
      return;
    }
    this.clearTimeoutFn(pending.timer);
    this.pending.delete(requestId);
  }

  private rejectAll(error: Error): void {
    const pending = [...this.pending.entries()];
    this.pending.clear();
    for (const [, item] of pending) {
      this.clearTimeoutFn(item.timer);
      item.reject(error);
    }
  }

  private emitProtocolError(error: ProtocolError): void {
    for (const handler of this.errorHandlers) {
      handler(error);
    }
  }
}
