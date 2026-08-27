import type { WireAlertCandidate } from "../protocol/types";

export const UNREAD_BADGE_CAP = 99;

export type AlertToastMode = "off" | "critical";

export function parseAlertToast(raw: unknown): AlertToastMode {
  return raw === "critical" ? "critical" : "off";
}

export function formatUnreadBadge(count: number): string | undefined {
  if (count <= 0) {
    return undefined;
  }
  if (count >= 100) {
    return `${UNREAD_BADGE_CAP}+`;
  }
  return String(count);
}

export function applyUnreadBadge(text: string, unread: number): string {
  const badge = formatUnreadBadge(unread);
  return badge === undefined ? text : `${text} · ${badge}`;
}

export function formatAlertDiagnostic(candidate: WireAlertCandidate): string {
  return `alert candidate symbol=${candidate.symbol} priority=${candidate.priority} family=${candidate.family}`;
}

export interface CriticalToastPlan {
  show: boolean;
  message?: string;
}

export function planCriticalToast(
  mode: AlertToastMode,
  candidates: readonly WireAlertCandidate[],
): CriticalToastPlan {
  if (mode !== "critical") {
    return { show: false };
  }
  const critical = candidates.filter((item) => item.priority === "critical");
  const first = critical[0];
  if (first === undefined) {
    return { show: false };
  }
  const head = `Market Sentinel: ${first.title}`;
  if (critical.length === 1) {
    return { show: true, message: head };
  }
  return { show: true, message: `${head} (+${critical.length - 1} more)` };
}
