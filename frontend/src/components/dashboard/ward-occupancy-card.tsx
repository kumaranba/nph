"use client";

import { useQuery } from "@apollo/client";

import { Card } from "@/components/ui/card";
import { LinesSkeleton, QueryError } from "@/components/query-states";
import { WARD_OCCUPANCY } from "@/lib/graphql/dashboard-operations";

type Bed = { id: string; label: string; status: string };
type Ward = { id: string; name: string; beds: Bed[] };

// status: OCCUPIED | VACANT | CLEANING | ATTENTION
function bedClass(status: string): string {
  switch (status) {
    case "OCCUPIED":
      return "bg-zinc-700 border-zinc-700";
    case "CLEANING":
      return "bg-amber-50 border-amber-200";
    case "ATTENTION":
      return "bg-red-50 border-red-200";
    default:
      return "bg-background border-input"; // VACANT
  }
}
const occupiedCount = (beds: Bed[]) =>
  beds.filter((b) => b.status === "OCCUPIED" || b.status === "ATTENTION").length;

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-[11px] w-[11px] rounded-[3px] border ${swatch}`} />
      {label}
    </span>
  );
}

export function WardOccupancyCard() {
  const { data, loading, error, refetch } = useQuery<{ wards: Ward[] }>(WARD_OCCUPANCY);
  const wards = data?.wards ?? [];
  const total = wards.reduce((n, w) => n + w.beds.length, 0);
  const occupied = wards.reduce((n, w) => n + occupiedCount(w.beds), 0);

  return (
    <Card className="p-[18px] shadow-none">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <div className="text-sm font-semibold">Ward occupancy</div>
          <div className="mt-0.5 text-[12.5px] text-muted-foreground">
            {occupied} of {total} beds occupied across {wards.length} wards
          </div>
        </div>
        <div className="hidden flex-wrap items-center gap-x-3.5 gap-y-1 text-[11.5px] text-muted-foreground sm:flex">
          <Legend swatch="bg-zinc-700 border-zinc-700" label="Occupied" />
          <Legend swatch="bg-background border-input" label="Vacant" />
          <Legend swatch="bg-amber-50 border-amber-200" label="Cleaning" />
          <Legend swatch="bg-red-50 border-red-200" label="Attention" />
        </div>
      </div>

      {loading ? (
        <LinesSkeleton lines={4} />
      ) : error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : (
        <div className="flex flex-col gap-4">
          {wards.map((w) => (
            <div key={w.id}>
              <div className="mb-2 flex items-baseline justify-between">
                <span className="text-[12.5px] font-semibold text-zinc-700">{w.name}</span>
                <span className="font-mono text-[11.5px] text-muted-foreground">
                  {occupiedCount(w.beds)} / {w.beds.length}
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {w.beds.map((b) => (
                  <div
                    key={b.id}
                    title={`${b.label} · ${b.status.toLowerCase()}`}
                    className={`h-[22px] w-[22px] rounded-[5px] border ${bedClass(b.status)}`}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
