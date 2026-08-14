"use client";

import { useQuery } from "@apollo/client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  EmptyState,
  QueryError,
  TableSkeleton,
} from "@/components/query-states";
import { getAccessToken } from "@/lib/auth";
import { FEES_DUE_LIST, ME, PENDING_DUES_LIST } from "@/lib/graphql/operations";

// Pending-dues report PDF lives on the same origin as the GraphQL endpoint.
const PDF_URL = (
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/"
).replace(/\/graphql\/?$/, "/reports/fees-due.pdf");

type PendingDueRow = {
  id: string;
  patientId: string;
  name: string;
  gender: string;
  room: string | null;
  admissionDate: string;
  currentFees: string;
  totalPendingDues: string;
  contact: string;
  place: string;
};
type PendingDuesResult = { pendingDuesList: PendingDueRow[] };

type FeeDueRow = {
  id: string;
  patientId: string;
  name: string;
  room: string | null;
  dueDate: string;
  amountDue: string;
  openingBalance: string;
  totalDueNow: string;
  daysUntilDue: number;
};

type FeesDueResult = { feesDueList: FeeDueRow[] };
type MeResult = { me: { id: string; email: string; role: string } };

function money(value: string) {
  return `₹${Number(value).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function FeesDuePage() {
  const router = useRouter();
  const [withinDaysInput, setWithinDaysInput] = useState("");
  const [sortAsc, setSortAsc] = useState(true);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data: meData, loading: meLoading } = useQuery<MeResult>(ME, {
    skip: !hasToken,
  });
  const role = meData?.me.role ?? "";
  const allowed = role === "ADMIN" || role === "FINANCE";

  // null → server falls back to the feeDueWarningDays system setting.
  const withinDays = withinDaysInput === "" ? null : Number(withinDaysInput);

  const { data, loading, error, refetch } = useQuery<FeesDueResult>(
    FEES_DUE_LIST,
    {
      variables: { withinDays },
      skip: !hasToken || !allowed,
    }
  );

  const rows = useMemo(() => {
    const list = [...(data?.feesDueList ?? [])];
    list.sort((a, b) =>
      sortAsc
        ? a.dueDate.localeCompare(b.dueDate)
        : b.dueDate.localeCompare(a.dueDate)
    );
    return list;
  }, [data, sortAsc]);

  // Pending dues (past + present), highest outstanding first.
  const {
    data: pendingData,
    loading: pendingLoading,
    error: pendingError,
    refetch: refetchPending,
  } = useQuery<PendingDuesResult>(PENDING_DUES_LIST, {
    skip: !hasToken || !allowed,
  });
  const pendingRows = pendingData?.pendingDuesList ?? [];
  const [downloading, setDownloading] = useState(false);

  async function downloadPdf() {
    const token = getAccessToken();
    if (!token) return;
    setDownloading(true);
    try {
      const resp = await fetch(PDF_URL, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(`Download failed (${resp.status})`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "fees-due.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Surfaced via the disabled state resetting; keep it simple.
    } finally {
      setDownloading(false);
    }
  }

  if (!hasToken || meLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-4 sm:p-6 lg:p-8">
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
              The fees-due list is available to Finance and Admin only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-3xl p-4 sm:p-6 lg:p-8">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Fees due</CardTitle>
              <CardDescription>
                Patients with an upcoming billing cycle date
              </CardDescription>
            </div>
            <Button asChild variant="outline">
              <Link href="/payments/new">Record payment</Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-end gap-2">
            <div className="space-y-2">
              <Label htmlFor="withinDays">Look-ahead (days)</Label>
              <Input
                id="withinDays"
                type="number"
                min={0}
                className="w-40"
                placeholder="Default"
                value={withinDaysInput}
                onChange={(e) => setWithinDaysInput(e.target.value)}
              />
            </div>
          </div>

          {loading ? (
            <TableSkeleton rows={4} cols={6} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No fees due"
              description="No patients have a billing cycle date in this window."
            />
          ) : (
            <>
              {/* Sort control (drives both card list and table). */}
              <button
                type="button"
                className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
                onClick={() => setSortAsc((v) => !v)}
              >
                Sort by due date {sortAsc ? "▲" : "▼"}
              </button>

              {/* Mobile: stacked cards */}
              <div className="space-y-2.5 sm:hidden">
                {rows.map((row) => (
                  <button
                    key={row.id}
                    type="button"
                    onClick={() => router.push(`/patients/${row.id}`)}
                    className="flex w-full items-start justify-between gap-3 rounded-lg border bg-card p-3 text-left active:bg-muted/50"
                  >
                    <div className="min-w-0">
                      <div className="font-medium">{row.name}</div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {row.patientId}
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                        <span>{row.room ?? "—"}</span>
                        <span>
                          Due{" "}
                          <b className="font-medium text-foreground">
                            {row.daysUntilDue === 0
                              ? "Today"
                              : `in ${row.daysUntilDue}d`}
                          </b>
                        </span>
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="font-semibold">{money(row.totalDueNow)}</div>
                      {Number(row.openingBalance) > 0 ? (
                        <div className="text-xs text-amber-700">
                          incl. {money(row.openingBalance)} opening
                        </div>
                      ) : null}
                      <div className="text-xs text-muted-foreground">
                        {row.dueDate}
                      </div>
                    </div>
                  </button>
                ))}
              </div>

              {/* Tablet/desktop: table */}
              <div className="hidden overflow-x-auto sm:block">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Patient</th>
                      <th className="py-2 pr-4 font-medium">ID</th>
                      <th className="py-2 pr-4 font-medium">Room</th>
                      <th className="py-2 pr-4 font-medium">Due date</th>
                      <th className="py-2 pr-4 font-medium">Days</th>
                      <th className="py-2 pr-4 text-right font-medium">Cycle</th>
                      <th className="py-2 pr-4 text-right font-medium">Opening bal.</th>
                      <th className="py-2 text-right font-medium">Total due</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr
                        key={row.id}
                        className="cursor-pointer border-b last:border-0 hover:bg-muted/50"
                        onClick={() => router.push(`/patients/${row.id}`)}
                      >
                        <td className="py-2 pr-4">{row.name}</td>
                        <td className="py-2 pr-4 font-mono text-xs">
                          {row.patientId}
                        </td>
                        <td className="py-2 pr-4">{row.room ?? "—"}</td>
                        <td className="py-2 pr-4">{row.dueDate}</td>
                        <td className="py-2 pr-4">
                          {row.daysUntilDue === 0
                            ? "Today"
                            : `${row.daysUntilDue}d`}
                        </td>
                        <td className="py-2 pr-4 text-right text-muted-foreground">
                          {money(row.amountDue)}
                        </td>
                        <td className="py-2 pr-4 text-right">
                          {Number(row.openingBalance) > 0 ? (
                            <span className="text-amber-700">
                              {money(row.openingBalance)}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="py-2 text-right font-semibold">
                          {money(row.totalDueNow)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Pending dues (past + present) — highest outstanding first, with PDF. */}
      <Card className="mt-6">
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Pending dues</CardTitle>
              <CardDescription>
                Active patients who owe money now (includes past dues), highest
                first
              </CardDescription>
            </div>
            <Button
              variant="outline"
              onClick={downloadPdf}
              disabled={downloading || pendingRows.length === 0}
            >
              {downloading ? "Preparing…" : "Download PDF"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {pendingLoading ? (
            <TableSkeleton rows={4} cols={5} />
          ) : pendingError ? (
            <QueryError
              message={pendingError.message}
              onRetry={() => refetchPending()}
            />
          ) : pendingRows.length === 0 ? (
            <EmptyState
              title="No pending dues"
              description="No active patient currently has an outstanding balance."
            />
          ) : (
            <>
              {/* Mobile: stacked cards */}
              <div className="space-y-2.5 sm:hidden">
                {pendingRows.map((row) => (
                  <button
                    key={row.id}
                    type="button"
                    onClick={() => router.push(`/patients/${row.id}`)}
                    className="flex w-full items-start justify-between gap-3 rounded-lg border bg-card p-3 text-left active:bg-muted/50"
                  >
                    <div className="min-w-0">
                      <div className="font-medium">{row.name}</div>
                      <div className="mt-1.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                        <span>{row.place || "—"}</span>
                        <span>{row.contact || "—"}</span>
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="font-semibold text-red-700">
                        {money(row.totalPendingDues)}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        cycle {money(row.currentFees)}
                      </div>
                    </div>
                  </button>
                ))}
              </div>

              {/* Tablet/desktop: table */}
              <div className="hidden overflow-x-auto sm:block">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">#</th>
                      <th className="py-2 pr-4 font-medium">Patient</th>
                      <th className="py-2 pr-4 font-medium">DOA</th>
                      <th className="py-2 pr-4 text-right font-medium">
                        Current fees
                      </th>
                      <th className="py-2 pr-4 text-right font-medium">
                        Total pending
                      </th>
                      <th className="py-2 pr-4 font-medium">Contact</th>
                      <th className="py-2 font-medium">Place</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingRows.map((row, i) => (
                      <tr
                        key={row.id}
                        className="cursor-pointer border-b last:border-0 hover:bg-muted/50"
                        onClick={() => router.push(`/patients/${row.id}`)}
                      >
                        <td className="py-2 pr-4 text-muted-foreground">
                          {i + 1}
                        </td>
                        <td className="py-2 pr-4">{row.name}</td>
                        <td className="py-2 pr-4">{row.admissionDate}</td>
                        <td className="py-2 pr-4 text-right">
                          {money(row.currentFees)}
                        </td>
                        <td className="py-2 pr-4 text-right font-semibold text-red-700">
                          {money(row.totalPendingDues)}
                        </td>
                        <td className="py-2 pr-4">{row.contact || "—"}</td>
                        <td className="py-2">{row.place || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
