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
import { FEES_DUE_LIST, ME } from "@/lib/graphql/operations";

type FeeDueRow = {
  id: string;
  patientId: string;
  name: string;
  room: string | null;
  dueDate: string;
  amountDue: string;
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

  if (!hasToken || meLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (!allowed) {
    return (
      <main className="mx-auto min-h-screen max-w-3xl p-8">
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
    <main className="mx-auto min-h-screen max-w-3xl p-8">
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
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Patient</th>
                    <th className="py-2 pr-4 font-medium">ID</th>
                    <th className="py-2 pr-4 font-medium">Room</th>
                    <th className="py-2 pr-4 font-medium">
                      <button
                        type="button"
                        className="flex items-center gap-1 font-medium hover:text-foreground"
                        onClick={() => setSortAsc((v) => !v)}
                      >
                        Due date {sortAsc ? "▲" : "▼"}
                      </button>
                    </th>
                    <th className="py-2 pr-4 font-medium">Days</th>
                    <th className="py-2 text-right font-medium">Amount due</th>
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
                      <td className="py-2 text-right">{money(row.amountDue)}</td>
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
