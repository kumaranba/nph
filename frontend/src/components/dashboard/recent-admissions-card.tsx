"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { LinesSkeleton, QueryError, EmptyState } from "@/components/query-states";
import { RECENT_ADMISSIONS } from "@/lib/graphql/dashboard-operations";
import { initials } from "@/components/dashboard/format";
import { formatDate } from "@/lib/format-date";

type Adm = {
  id: string;
  admissionDate: string;
  admittingDoctor: string | null;
  patient: {
    id: string;
    patientId: string;
    name: string;
    age: number | null;
    diagnosis: string | null;
  };
  bed: { label: string; room: { name: string } | null } | null;
};

export function RecentAdmissionsCard() {
  const router = useRouter();
  const { data, loading, error, refetch } = useQuery<{ recentAdmissions: Adm[] }>(
    RECENT_ADMISSIONS,
    { variables: { limit: 4 } }
  );
  const rows = data?.recentAdmissions ?? [];

  return (
    <Card className="p-[18px] shadow-none">
      <div className="mb-3.5 flex items-center justify-between">
        <span className="text-sm font-semibold">Recent admissions</span>
        <Link
          href="/admissions/new"
          className="text-[12.5px] font-medium text-muted-foreground hover:text-foreground"
        >
          View all
        </Link>
      </div>

      {loading ? (
        <LinesSkeleton lines={4} />
      ) : error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title="No recent admissions" />
      ) : (
        <div className="flex flex-col gap-3.5">
          {rows.map((a) => (
            <div
              key={a.id}
              onClick={() => router.push(`/patients/${a.patient.id}`)}
              className="flex cursor-pointer items-center gap-3"
            >
              <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
                {initials(a.patient.name)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-semibold">
                  {a.patient.name}
                  {a.patient.age != null ? (
                    <span className="font-normal text-muted-foreground"> · {a.patient.age}</span>
                  ) : null}
                </div>
                <div className="truncate text-[11.5px] text-muted-foreground">
                  {a.patient.diagnosis ?? "—"}
                  {a.admittingDoctor ? ` · ${a.admittingDoctor}` : ""}
                </div>
              </div>
              <div className="shrink-0 text-right">
                {a.bed ? (
                  <span className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                    {a.bed.label}
                  </span>
                ) : null}
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {formatDate(a.admissionDate)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
