"use client";

import { useQuery } from "@apollo/client";

import { Card } from "@/components/ui/card";
import { LinesSkeleton, QueryError, EmptyState } from "@/components/query-states";
import { FLAGGED_VITALS_FEED } from "@/lib/graphql/dashboard-operations";
import { formatClock } from "@/components/dashboard/format";

type Flag = {
  id: string;
  patientName: string;
  room: string | null;
  vital: string; // "BP" | "SpO₂" | "Pulse" | "Temp" ...
  value: string; // "168/104", "91%", "38.4°"
  direction: string; // "HIGH" | "LOW"
  severity: string; // "CRITICAL" | "WARNING"
  recordedAt: string;
};

function tone(severity: string): string {
  return severity === "CRITICAL" ? "text-red-600" : "text-amber-700";
}
function arrow(direction: string): string {
  return direction === "LOW" ? "▼ low" : "▲ high";
}

export function FlaggedVitalsCard() {
  const { data, loading, error, refetch } = useQuery<{ flaggedVitals: Flag[] }>(
    FLAGGED_VITALS_FEED,
    { variables: { limit: 6 } }
  );
  const rows = data?.flaggedVitals ?? [];

  return (
    <Card className="p-[18px] shadow-none">
      <div className="mb-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-[7px] w-[7px] rounded-full bg-red-500" />
          <span className="text-sm font-semibold">Flagged vitals</span>
        </div>
        <span className="text-xs text-muted-foreground">Live</span>
      </div>

      {loading ? (
        <LinesSkeleton lines={4} />
      ) : error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title="No flagged vitals" description="All readings within range." />
      ) : (
        <div className="flex flex-col">
          {rows.map((r, i) => (
            <div
              key={r.id}
              className={`flex items-center gap-3 py-2 ${
                i < rows.length - 1 ? "border-b border-muted" : ""
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold">{r.patientName}</div>
                <div className="text-[11.5px] text-muted-foreground">
                  {r.room ?? "—"} · {formatClock(r.recordedAt)}
                </div>
              </div>
              <div className="text-right">
                <span className={`font-mono text-[13px] font-semibold ${tone(r.severity)}`}>
                  {r.value}
                </span>
                <div className={`text-[11px] ${tone(r.severity)}`}>
                  {r.vital} {arrow(r.direction)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
