export const NA = "N/A";

export function formatPercent(value: number | null): string {
  if (value === null) {
    return NA;
  }
  const scaled = value * 100;
  if (scaled === 0) {
    return "+0.00%";
  }
  return `${scaled > 0 ? "+" : ""}${scaled.toFixed(2)}%`;
}

export function formatRatio(value: number | null): string {
  if (value === null) {
    return NA;
  }
  return `${value.toFixed(2)}x`;
}

export function formatRsi(value: number | null): string {
  if (value === null) {
    return NA;
  }
  return value.toFixed(1);
}

export function formatPrice(value: number | null): string {
  if (value === null) {
    return NA;
  }
  return value.toFixed(2);
}

export function escapeMarkdown(text: string): string {
  return text.replace(/[\r\n]+/g, " ").replace(/[\\`*_{}[\]()#+!|><-]/g, "\\$&");
}
