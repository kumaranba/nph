"use client";

import { useQuery } from "@apollo/client";
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
import { ME, PAYMENT_RECEIPTS } from "@/lib/graphql/operations";

type Receipt = {
  id: string;
  patientPk: string;
  patientName: string;
  patientCode: string;
  paidOn: string;
  amount: string;
  feesAmount: string;
  chargesAmount: string;
  account: { name: string } | null;
};

type ReceiptsResult = { paymentReceipts: Receipt[] };
type MeResult = { me: { role: string } };

// Same-origin receipt PDF endpoint, derived from the GraphQL endpoint.
const RECEIPT_BASE = (
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/"
).replace(/\/graphql\/?$/, "/reports/receipt/");

function money(v: string | number) {
  return `₹${Number(v).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function PaymentsHistoryPage() {
  const router = useRouter();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data: meData, loading: meLoading } = useQuery<MeResult>(ME, {
    skip: !hasToken,
  });
  const allowed = meData?.me.role === "ADMIN" || meData?.me.role === "FINANCE";

  const { data, loading, error, refetch } = useQuery<ReceiptsResult>(
    PAYMENT_RECEIPTS,
    {
      variables: { from: from || null, to: to || null },
      skip: !hasToken || !allowed,
    }
  );

  const rows = data?.paymentReceipts ?? [];
  const total = useMemo(
    () => rows.reduce((sum, r) => sum + Number(r.amount), 0),
    [rows]
  );

  async function downloadReceipt(id: string) {
    const token = getAccessToken();
    if (!token) return;
    const resp = await fetch(`${RECEIPT_BASE}${id}.pdf`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `receipt-${id}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }

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
              Payments history is available to Finance and Admin only.
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
          <CardTitle>Payments history</CardTitle>
          <CardDescription>Payments received, with receipts</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="from">From</Label>
              <Input
                id="from"
                type="date"
                className="w-44"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="to">To</Label>
              <Input
                id="to"
                type="date"
                className="w-44"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </div>
          </div>

          {loading ? (
            <TableSkeleton rows={5} cols={5} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No payments"
              description="No payments were received in this range."
            />
          ) : (
            <>
              <div className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2 text-sm">
                <span className="text-muted-foreground">
                  {rows.length} payment{rows.length === 1 ? "" : "s"}
                </span>
                <span className="font-semibold">Total {money(total)}</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Date</th>
                      <th className="py-2 pr-4 font-medium">Patient</th>
                      <th className="py-2 pr-4 font-medium">Account</th>
                      <th className="py-2 pr-4 text-right font-medium">Fees</th>
                      <th className="py-2 pr-4 text-right font-medium">Charges</th>
                      <th className="py-2 pr-4 text-right font-medium">Total</th>
                      <th className="py-2 font-medium" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id} className="border-b last:border-0">
                        <td className="py-2 pr-4 whitespace-nowrap">{r.paidOn}</td>
                        <td className="py-2 pr-4">
                          <button
                            type="button"
                            className="text-left hover:underline"
                            onClick={() => router.push(`/patients/${r.patientPk}`)}
                          >
                            {r.patientName}
                            <span className="block font-mono text-xs text-muted-foreground">
                              {r.patientCode}
                            </span>
                          </button>
                        </td>
                        <td className="py-2 pr-4">{r.account?.name ?? "—"}</td>
                        <td className="py-2 pr-4 text-right">{money(r.feesAmount)}</td>
                        <td className="py-2 pr-4 text-right">{money(r.chargesAmount)}</td>
                        <td className="py-2 pr-4 text-right font-semibold">
                          {money(r.amount)}
                        </td>
                        <td className="py-2 text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => downloadReceipt(r.id)}
                          >
                            Receipt
                          </Button>
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
    </main>
  );
}
