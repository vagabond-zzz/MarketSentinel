export const NA = "--";
export const DASH = "--";

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return DASH;
  }
  const scaled = value * 100;
  if (scaled === 0) {
    return "+0.00%";
  }
  return `${scaled > 0 ? "+" : ""}${scaled.toFixed(2)}%`;
}

export function formatRatio(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return DASH;
  }
  return `${value.toFixed(2)}x`;
}

export function formatRsi(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return DASH;
  }
  return value.toFixed(1);
}

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return DASH;
  }
  return value.toFixed(2);
}

export function formatClock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return DASH;
  }
  const date = new Date(seconds * 1000);
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  const ss = String(date.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function formatDirection(direction: string): string {
  if (direction === "up") {
    return "↑";
  }
  if (direction === "down") {
    return "↓";
  }
  return "·";
}

export function fallbackReasonLabel(reason: string | undefined): string | undefined {
  if (reason === undefined || reason.length === 0) {
    return undefined;
  }
  if (reason === "timeout") {
    return "timeout";
  }
  if (reason === "malformed") {
    return "parse_error";
  }
  if (
    reason === "transport" ||
    reason === "unavailable" ||
    reason === "rate_limited" ||
    reason === "provider_error"
  ) {
    return "provider_error";
  }
  if (reason === "parse_error") {
    return "parse_error";
  }
  return undefined;
}

export function escapeMarkdown(text: string): string {
  return text.replace(/[\r\n]+/g, " ").replace(/[\\`*_{}[\]()#+!|><-]/g, "\\$&");
}
