"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/card";
import { LinesSkeleton, QueryError } from "@/components/query-states";
import { initials } from "@/components/dashboard/format";
import { formatDate } from "@/lib/format-date";
import { FORCE_DISCHARGE_DUE_LIST } from "@/lib/graphql/dashboard-operations";

type Row = {
  forceDischargeDate: string;
  daysRemaining: number;
  admission: {
    id: string;
    admissionDate: string;
    patient: { id: string; patientId: string; name: string };
    bed: { label: string; room: { name: string } | null } | null;
  };
};

export function ForceDischargeCard() {
  const router = useRouter();
  const { data, loading, error, refetch } = useQuery<{
    forceDischargeDueList: Row[];
  }>(FORCE_DISCHARGE_DUE_LIST);
  const rows = data?.forceDischargeDueList ?? [];

  // The card hides itself when the limit is disabled or nothing is due, so it
  // doesn't take up space for deployments that don't use the limit.
  if (!loading && !error && rows.length === 0) return null;

  return (
    <Card className="p-[18px] shadow-none">
      <div className="mb-3.5 flex items-center justify-between">
        <span className="text-sm font-semibold">Force discharge due · next 30 days</span>
        <span className="text-[12.5px] text-muted-foreground">{rows.length}</span>
      </div>

      {loading ? (
        <LinesSkeleton lines={3} />
      ) : error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : (
        <div className="flex flex-col gap-3.5">
          {rows.map((r) => {
            const overdue = r.daysRemaining < 0;
            return (
              <div
                key={r.admission.id}
                onClick={() => router.push(`/patients/${r.admission.patient.id}`)}
                className="flex cursor-pointer items-center gap-3"
              >
                <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
                  {initials(r.admission.patient.name)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] font-semibold">
                    {r.admission.patient.name}
                  </div>
                  <div className="truncate text-[11.5px] text-muted-foreground">
                    Admitted {formatDate(r.admission.admissionDate)} · limit{" "}
                    {formatDate(r.forceDischargeDate)}
                  </div>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                    overdue
                      ? "bg-red-100 text-red-700"
                      : "bg-amber-100 text-amber-800"
                  }`}
                >
                  {overdue
                    ? `${-r.daysRemaining}d overdue`
                    : `${r.daysRemaining}d left`}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
