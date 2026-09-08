"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/card";
import { LinesSkeleton, QueryError } from "@/components/query-states";
import { initials } from "@/components/dashboard/format";
import { formatDate } from "@/lib/format-date";
import { UPCOMING_BIRTHDAYS } from "@/lib/graphql/dashboard-operations";

type Row = {
  birthday: string;
  turningAge: number;
  daysUntil: number;
  bedLabel: string | null;
  patient: { id: string; patientId: string; name: string };
};

export function BirthdayCard() {
  const router = useRouter();
  const { data, loading, error, refetch } = useQuery<{
    upcomingBirthdays: Row[];
  }>(UPCOMING_BIRTHDAYS);
  const rows = data?.upcomingBirthdays ?? [];

  // Hide when nothing's coming up, so it doesn't sit empty on the board.
  if (!loading && !error && rows.length === 0) return null;

  return (
    <Card className="p-[18px] shadow-none">
      <div className="mb-3.5 flex items-center justify-between">
        <span className="text-sm font-semibold">Birthdays · next 7 days</span>
        <span className="text-[12.5px] text-muted-foreground">{rows.length}</span>
      </div>

      {loading ? (
        <LinesSkeleton lines={3} />
      ) : error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : (
        <div className="flex flex-col gap-3.5">
          {rows.map((r) => (
            <div
              key={r.patient.id}
              onClick={() => router.push(`/patients/${r.patient.id}`)}
              className="flex cursor-pointer items-center gap-3"
            >
              <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
                {initials(r.patient.name)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold">
                  {r.patient.name}
                  <span className="font-normal text-muted-foreground">
                    {" "}· turning {r.turningAge}
                  </span>
                </div>
                <div className="truncate text-[11.5px] text-muted-foreground">
                  {formatDate(r.birthday)}
                  {r.bedLabel ? ` · ${r.bedLabel}` : ""}
                </div>
              </div>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  r.daysUntil === 0
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {r.daysUntil === 0 ? "Today" : `in ${r.daysUntil}d`}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
