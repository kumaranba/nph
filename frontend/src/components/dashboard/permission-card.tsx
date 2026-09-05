"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/card";
import { LinesSkeleton, QueryError, EmptyState } from "@/components/query-states";
import { initials } from "@/components/dashboard/format";
import { formatDate } from "@/lib/format-date";
import { PATIENTS_ON_PERMISSION } from "@/lib/graphql/operations";

type Row = {
  id: string;
  startDate: string;
  expectedReturn: string | null;
  admission: {
    id: string;
    patient: { id: string; patientId: string; name: string; gender: string };
    bed: { label: string; room: { name: string } | null } | null;
  };
};

export function PermissionCard() {
  const router = useRouter();
  const { data, loading, error, refetch } = useQuery<{
    patientsOnPermission: Row[];
  }>(PATIENTS_ON_PERMISSION);
  const rows = data?.patientsOnPermission ?? [];

  return (
    <Card className="p-[18px] shadow-none">
      <div className="mb-3.5 flex items-center justify-between">
        <span className="text-sm font-semibold">On permission</span>
        <span className="text-[12.5px] text-muted-foreground">{rows.length}</span>
      </div>

      {loading ? (
        <LinesSkeleton lines={3} />
      ) : error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title="No patients on permission" />
      ) : (
        <div className="flex flex-col gap-3.5">
          {rows.map((r) => (
            <div
              key={r.id}
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
                  Out since {formatDate(r.startDate)}
                  {r.expectedReturn
                    ? ` · back ${formatDate(r.expectedReturn)}`
                    : ""}
                </div>
              </div>
              {r.admission.bed ? (
                <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                  {r.admission.bed.label}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
