"use client";

import { useQuery } from "@apollo/client";
import { useState } from "react";

import { QueryError } from "@/components/query-states";
import { Button } from "@/components/ui/button";
import { getAccessToken } from "@/lib/auth";
import { formatDate } from "@/lib/format-date";
import { FOOD_VENDOR_LIST } from "@/lib/graphql/operations";

const API_ORIGIN = (
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/"
).replace(/\/graphql\/?$/, "");

type Row = { day: string; patients: number; rate: string; amount: string };
type Result = {
  foodVendorList: {
    dateFrom: string;
    dateTo: string;
    totalPatientDays: number;
    totalAmount: string;
    rows: Row[];
  };
};

const rupee = (n: string | number) =>
  `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

// First day of the current month and today, as YYYY-MM-DD.
function defaultRange() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { from: iso(first), to: iso(now) };
}

export function FoodVendorListReport() {
  const init = defaultRange();
  const [from, setFrom] = useState(init.from);
  const [to, setTo] = useState(init.to);

  const { data, loading, error, refetch } = useQuery<Result>(FOOD_VENDOR_LIST, {
    variables: { from, to },
    fetchPolicy: "cache-and-network",
  });

  const list = data?.foodVendorList;

  async function downloadPdf() {
    const token = getAccessToken();
    if (!token) return;
    const qs = new URLSearchParams({ from, to });
    const resp = await fetch(`${API_ORIGIN}/reports/food-vendor.pdf?${qs}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `food-vendor-${from}-to-${to}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-end gap-2">
          <label className="space-y-1.5 text-sm">
            <span className="font-medium text-muted-foreground">From</span>
            <input
              type="date"
              value={from}
              max={to}
              onChange={(e) => setFrom(e.target.value)}
              className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <label className="space-y-1.5 text-sm">
            <span className="font-medium text-muted-foreground">To</span>
            <input
              type="date"
              value={to}
              min={from}
              onChange={(e) => setTo(e.target.value)}
              className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
        </div>
        <Button variant="outline" size="sm" onClick={downloadPdf} disabled={!list}>
          Download PDF
        </Button>
      </div>

      {error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : loading && !list ? (
        <p className="py-4 text-sm text-muted-foreground">Loading…</p>
      ) : !list || list.rows.length === 0 ? (
        <p className="py-4 text-sm text-muted-foreground">
          No patient-days in this range.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-4 font-medium">Date</th>
                <th className="py-2 pr-4 text-right font-medium">Patients</th>
                <th className="py-2 pr-4 text-right font-medium">Rate/day</th>
                <th className="py-2 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody>
              {list.rows.map((r) => (
                <tr key={r.day} className="border-b last:border-0">
                  <td className="py-1.5 pr-4 whitespace-nowrap">
                    {formatDate(r.day)}
                  </td>
                  <td className="py-1.5 pr-4 text-right">{r.patients}</td>
                  <td className="py-1.5 pr-4 text-right">{rupee(r.rate)}</td>
                  <td className="py-1.5 text-right">{rupee(r.amount)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 font-semibold">
                <td className="py-2 pr-4">Total</td>
                <td className="py-2 pr-4 text-right">{list.totalPatientDays}</td>
                <td className="py-2 pr-4"></td>
                <td className="py-2 text-right text-primary">
                  {rupee(list.totalAmount)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
