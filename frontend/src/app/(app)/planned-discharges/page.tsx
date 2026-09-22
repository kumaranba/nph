"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  EmptyState,
  QueryError,
  TableSkeleton,
} from "@/components/query-states";
import { getAccessToken } from "@/lib/auth";
import { PLANNED_DISCHARGE_LIST, ME } from "@/lib/graphql/operations";
import { formatDate } from "@/lib/format-date";

type Row = {
  plannedDischargeDate: string;
  daysRemaining: number;
  isOverdue: boolean;
  admission: {
    id: string;
    admissionDate: string;
    patient: { id: string; patientId: string; name: string };
    bed: { id: string; label: string; room: { id: string; name: string } } | null;
  };
};

type Result = { plannedDischargeList: Row[] };
type MeResult = { me: { role: string } };

function whenLabel(days: number): string {
  if (days < 0) return `${-days} day${days === -1 ? "" : "s"} overdue`;
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  return `in ${days} days`;
}

export default function PlannedDischargesPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data: meData, loading: meLoading } = useQuery<MeResult>(ME, {
    skip: !hasToken,
  });
  const allowed = meData?.me.role === "ADMIN" || meData?.me.role === "PRO";

  const { data, loading, error, refetch } = useQuery<Result>(
    PLANNED_DISCHARGE_LIST,
    {
      variables: {
        search: search || null,
        plannedFrom: from || null,
        plannedTo: to || null,
        overdueOnly,
      },
      skip: !hasToken || !allowed,
      fetchPolicy: "cache-and-network",
    }
  );
  const rows = data?.plannedDischargeList ?? [];
  const overdueCount = rows.filter((r) => r.isOverdue).length;

  if (!hasToken || meLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-4">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (!allowed) {
    return (
      <main className="mx-auto min-h-screen max-w-3xl p-4 sm:p-6 lg:p-8">
        <Card>
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
            <CardDescription>
              Planned discharges are available to Admin and Patient Relations.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl p-4 sm:p-6 lg:p-8">
      <Card>
        <CardHeader>
          <CardTitle>Planned discharges</CardTitle>
          <CardDescription>
            Upcoming bed vacancies from administration&rsquo;s planned discharge
            dates.
            {overdueCount > 0 ? (
              <span className="ml-1 font-medium text-red-600">
                {overdueCount} overdue.
              </span>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[180px] flex-1 space-y-1.5">
              <span className="text-sm font-medium text-muted-foreground">
                Patient
              </span>
              <input
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Name or ID…"
              />
            </div>
            <div className="space-y-1.5">
              <span className="text-sm font-medium text-muted-foreground">
                Planned from
              </span>
              <input
                type="date"
                className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={from}
                max={to || undefined}
                onChange={(e) => setFrom(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <span className="text-sm font-medium text-muted-foreground">to</span>
              <input
                type="date"
                className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={to}
                min={from || undefined}
                onChange={(e) => setTo(e.target.value)}
              />
            </div>
            <label className="flex h-9 items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={overdueOnly}
                onChange={(e) => setOverdueOnly(e.target.checked)}
              />
              Overdue only
            </label>
          </div>

          {loading && rows.length === 0 ? (
            <TableSkeleton rows={5} cols={4} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No planned discharges"
              description={
                search || from || to || overdueOnly
                  ? "No planned discharges match your filters."
                  : "No discharge dates have been planned yet."
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Patient</th>
                    <th className="py-2 pr-4 font-medium">Bed</th>
                    <th className="py-2 pr-4 font-medium">Planned</th>
                    <th className="py-2 font-medium">When</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={r.admission.id}
                      className={`cursor-pointer border-b last:border-0 hover:bg-muted/50 ${
                        r.isOverdue ? "bg-red-50/60" : ""
                      }`}
                      onClick={() =>
                        router.push(`/patients/${r.admission.patient.id}`)
                      }
                    >
                      <td className="py-2 pr-4">
                        {r.admission.patient.name}
                        <span className="block font-mono text-xs text-muted-foreground">
                          {r.admission.patient.patientId}
                        </span>
                      </td>
                      <td className="py-2 pr-4 whitespace-nowrap">
                        {r.admission.bed
                          ? `${r.admission.bed.room.name} · ${r.admission.bed.label}`
                          : "—"}
                      </td>
                      <td className="py-2 pr-4 whitespace-nowrap">
                        {formatDate(r.plannedDischargeDate)}
                      </td>
                      <td className="py-2 whitespace-nowrap">
                        {r.isOverdue ? (
                          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
                            Discharge due · {whenLabel(r.daysRemaining)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">
                            {whenLabel(r.daysRemaining)}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
