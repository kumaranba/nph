// Project-wide date display: always DD-MM-YYYY.
//
// The API sends dates as ISO "YYYY-MM-DD" (and datetimes as ISO 8601). We parse
// the date part directly (no `new Date()`) so the shown day never shifts across
// timezones.

/** ISO date/datetime -> "DD-MM-YYYY". Empty/invalid -> "—". */
export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value));
  if (!m) return String(value);
  return `${m[3]}-${m[2]}-${m[1]}`;
}

/** ISO datetime -> "DD-MM-YYYY, HH:MM" (24h, local time). Invalid -> raw. */
export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return String(value);
  const p = (n: number) => String(n).padStart(2, "0");
  return (
    `${p(d.getDate())}-${p(d.getMonth() + 1)}-${d.getFullYear()}, ` +
    `${p(d.getHours())}:${p(d.getMinutes())}`
  );
}
