/** ₹ with grouped thousands (Indian numbering), no decimals. */
export function formatINR(value: number | string): string {
  const n = Number(value);
  if (!isFinite(n)) return "—";
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

/** Compact ₹ for KPI values: 486200 -> "₹4.86L", 12000 -> "₹12.0K". */
export function formatLakh(value: number | string): string {
  const n = Number(value);
  if (!isFinite(n)) return "—";
  if (Math.abs(n) >= 100000) return `₹${(n / 100000).toFixed(2)}L`;
  if (Math.abs(n) >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${n.toFixed(0)}`;
}

/** ISO timestamp -> "09:15" (24h). Falls back to the raw string. */
export function formatClock(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Initials from a person's name (max 2 chars). */
export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}
