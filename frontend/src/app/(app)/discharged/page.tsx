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
import { TagChip, TagInput } from "@/components/tag-input";
import {
  EmptyState,
  QueryError,
  TableSkeleton,
} from "@/components/query-states";
import { getAccessToken } from "@/lib/auth";
import {
  DISCHARGED_LIST,
  DISCHARGED_MONTHLY_SUMMARY,
  ME,
} from "@/lib/graphql/operations";
import { formatDate } from "@/lib/format-date";

type Row = {
  id: string;
  patientId: string;
  name: string;
  admissionDate: string;
  dischargeDate: string | null;
  dischargeType: string;
  room: string | null;
  tags: string[];
};

type Result = { dischargedList: Row[] };
type MeResult = { me: { role: string } };
type MonthRow = { month: string; count: number };
type SummaryResult = { dischargedMonthlySummary: MonthRow[] };

// "2026-06" -> "Jun 2026"
function monthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return new Date(y, m - 1, 1).toLocaleDateString("en-GB", {
    month: "short",
    year: "numeric",
  });
}

export default function DischargedPage() {
  const router = useRouter();
  const [tag, setTag] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [sortDesc, setSortDesc] = useState(true);
  const [summaryOpen, setSummaryOpen] = useState(false);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data: meData, loading: meLoading } = useQuery<MeResult>(ME, {
    skip: !hasToken,
  });
  const allowed =
    meData?.me.role === "ADMIN" ||
    meData?.me.role === "FINANCE" ||
    meData?.me.role === "PRO";

  const { data, loading, error, refetch } = useQuery<Result>(DISCHARGED_LIST, {
    variables: {
      tag: tag || null,
      search: search || null,
      dischargedFrom: from || null,
      dischargedTo: to || null,
      sortDesc,
    },
    skip: !hasToken || !allowed,
  });
  const rows = data?.dischargedList ?? [];

  const { data: summaryData } = useQuery<SummaryResult>(
    DISCHARGED_MONTHLY_SUMMARY,
    { skip: !hasToken || !allowed }
  );
  const months = summaryData?.dischargedMonthlySummary ?? [];

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
              The discharged-patient list is available to Admin, Finance and
              Patient Relations only.
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
          <CardTitle>Discharged patients</CardTitle>
          <CardDescription>
            Filter by name, tag or discharge date. Re-admitted patients are not
            listed here.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[180px] flex-1 space-y-1.5">
              <span className="text-sm font-medium text-muted-foreground">
                Patient name
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
                Discharged from
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
              <span className="text-sm font-medium text-muted-foreground">
                to
              </span>
              <input
                type="date"
                className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={to}
                min={from || undefined}
                onChange={(e) => setTo(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-[220px] space-y-1.5">
              <span className="text-sm font-medium text-muted-foreground">
                Filter by tag
              </span>
              {tag ? (
                <div className="flex items-center gap-2">
                  <TagChip label={tag} onRemove={() => setTag(null)} />
                </div>
              ) : (
                <TagInput
                  allowCreate={false}
                  placeholder="Filter by a tag…"
                  onSelect={(label) => setTag(label)}
                />
              )}
            </div>
            <button
              type="button"
              className="text-xs font-medium text-muted-foreground hover:text-foreground"
              onClick={() => setSortDesc((v) => !v)}
            >
              Discharge date {sortDesc ? "▼ newest" : "▲ oldest"}
            </button>
          </div>

          {months.length > 0 ? (
            <div className="rounded-md border">
              <button
                type="button"
                className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium hover:bg-muted/50"
                onClick={() => setSummaryOpen((v) => !v)}
                aria-expanded={summaryOpen}
              >
                <span>
                  Monthly discharge summary
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    {months.reduce((n, m) => n + m.count, 0)} total ·{" "}
                    {months.length} month{months.length === 1 ? "" : "s"}
                  </span>
                </span>
                <span className="text-muted-foreground">{summaryOpen ? "▲" : "▼"}</span>
              </button>
              {summaryOpen ? (
                <div className="grid grid-cols-2 gap-x-6 gap-y-1 border-t px-3 py-2 text-sm sm:grid-cols-3">
                  {months.map((m) => (
                    <div key={m.month} className="flex justify-between">
                      <span className="text-muted-foreground">{monthLabel(m.month)}</span>
                      <span className="font-medium tabular-nums">{m.count}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {loading ? (
            <TableSkeleton rows={5} cols={5} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No discharged patients"
              description={
                tag || search || from || to
                  ? "No discharged patients match your filters."
                  : "No discharged patients yet."
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Patient</th>
                    <th className="py-2 pr-4 font-medium">Admitted</th>
                    <th className="py-2 pr-4 font-medium">Discharged</th>
                    <th className="py-2 pr-4 font-medium">Type</th>
                    <th className="py-2 font-medium">Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={`${r.id}-${r.dischargeDate}`}
                      className="cursor-pointer border-b last:border-0 hover:bg-muted/50"
                      onClick={() => router.push(`/patients/${r.id}`)}
                    >
                      <td className="py-2 pr-4">
                        {r.name}
                        <span className="block font-mono text-xs text-muted-foreground">
                          {r.patientId}
                        </span>
                      </td>
                      <td className="py-2 pr-4 whitespace-nowrap">
                        {formatDate(r.admissionDate)}
                      </td>
                      <td className="py-2 pr-4 whitespace-nowrap">
                        {r.dischargeDate ? formatDate(r.dischargeDate) : "—"}
                      </td>
                      <td className="py-2 pr-4">{r.dischargeType || "—"}</td>
                      <td className="py-2">
                        {r.tags.length > 0 ? (
                          <span className="flex flex-wrap gap-1">
                            {r.tags.map((t) => (
                              <TagChip key={t} label={t} />
                            ))}
                          </span>
                        ) : (
                          "—"
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
