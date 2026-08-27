export class ProtocolError extends Error {
  readonly code: string;
  readonly requestId?: string;

  constructor(code: string, message: string, requestId?: string) {
    super(message);
    this.name = "ProtocolError";
    this.code = code;
    this.requestId = requestId;
  }
}

export class IpcTimeoutError extends Error {
  readonly requestId: string;

  constructor(requestId: string, timeoutMs: number) {
    super(`request ${requestId} timed out after ${timeoutMs}ms`);
    this.name = "IpcTimeoutError";
    this.requestId = requestId;
  }
}

export class IpcDisconnectedError extends Error {
  constructor(message = "ipc disconnected") {
    super(message);
    this.name = "IpcDisconnectedError";
  }
}
