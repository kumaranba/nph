"use client";

import { useQuery } from "@apollo/client";

import { Card } from "@/components/ui/card";
import { LinesSkeleton, QueryError, EmptyState } from "@/components/query-states";
import { ACTIVITY_LOG } from "@/lib/graphql/dashboard-operations";
import { formatClock } from "@/components/dashboard/format";

type Act = {
  id: string;
  kind: string; // PAYMENT | VITAL | ADMISSION | INVOICE | DISCHARGE
  message: string;
  actor: string | null;
  createdAt: string;
};

function dotColor(kind: string): string {
  switch (kind) {
    case "PAYMENT":
      return "bg-emerald-600";
    case "VITAL":
      return "bg-red-500";
    case "ADMISSION":
      return "bg-zinc-600";
    default:
      return "bg-zinc-400"; // INVOICE / DISCHARGE / other
  }
}

export function ActivityCard() {
  const { data, loading, error, refetch } = useQuery<{ activityLog: Act[] }>(
    ACTIVITY_LOG,
    { variables: { limit: 6 } }
  );
  const rows = data?.activityLog ?? [];

  return (
    <Card className="p-[18px] shadow-none">
      <div className="mb-4 text-sm font-semibold">Recent activity</div>

      {loading ? (
        <LinesSkeleton lines={5} />
      ) : error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title="No activity yet" />
      ) : (
        <div className="flex flex-col">
          {rows.map((a, i) => (
            <div key={a.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span className={`mt-[3px] h-[9px] w-[9px] shrink-0 rounded-full ${dotColor(a.kind)}`} />
                {i < rows.length - 1 ? <span className="mt-0.5 w-[1.5px] flex-1 bg-muted" /> : null}
              </div>
              <div className={`min-w-0 ${i < rows.length - 1 ? "pb-4" : ""}`}>
                <div className="text-[12.5px] leading-snug">{a.message}</div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {a.actor ? `${a.actor} · ` : ""}
                  {formatClock(a.createdAt)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
