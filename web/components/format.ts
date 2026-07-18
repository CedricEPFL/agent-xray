export function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function percent(value: number | null | undefined, digits = 1): string {
  return finite(value) ? `${(value * 100).toFixed(digits)}%` : "—";
}

export function pp(value: number | null | undefined, digits = 1): string {
  return finite(value) ? `${value >= 0 ? "+" : ""}${value.toFixed(digits)} pp` : "—";
}

export function usd(value: number | null | undefined): string {
  if (!finite(value)) return "—";
  if (value === 0) return "$0.000000";
  return `$${value.toFixed(value < 0.01 ? 6 : 3)}`;
}

export function compactUsd(value: number): string {
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.01) return `$${value.toFixed(3)}`;
  return `$${value.toPrecision(2)}`;
}
