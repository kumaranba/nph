"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { QueryError } from "@/components/query-states";
import { Button } from "@/components/ui/button";
import { getAccessToken } from "@/lib/auth";
import { PATIENT_FOOD_REPORT } from "@/lib/graphql/operations";

const API_ORIGIN = (
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/"
).replace(/\/graphql\/?$/, "");

type Row = {
  patientPk: string;
  patientCode: string;
  name: string;
  days: number;
  rate: string;
  amount: string;
};
type Group = {
  key: string;
  label: string;
  totalDays: number;
  totalAmount: string;
  rows: Row[];
};
type Result = {
  patientFoodReport: {
    month: string;
    rate: string;
    grandTotalDays: number;
    grandTotalAmount: string;
    groups: Group[];
  };
};

const rupee = (n: string | number) =>
  `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

const currentMonth = () => new Date().toISOString().slice(0, 7);

export function PatientFoodReport() {
  const router = useRouter();
  const [month, setMonth] = useState(currentMonth());

  const { data, loading, error, refetch } = useQuery<Result>(
    PATIENT_FOOD_REPORT,
    { variables: { month }, fetchPolicy: "cache-and-network" }
  );

  const report = data?.patientFoodReport;

  async function downloadPdf() {
    const token = getAccessToken();
    if (!token) return;
    const qs = new URLSearchParams({ month });
    const resp = await fetch(`${API_ORIGIN}/reports/patient-food.pdf?${qs}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `patient-food-${month}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="space-y-1.5 text-sm">
          <span className="font-medium text-muted-foreground">Month</span>
          <input
            type="month"
            value={month}
            max={currentMonth()}
            onChange={(e) => setMonth(e.target.value)}
            className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>
        <div className="flex items-center gap-3">
          {report ? (
            <span className="text-xs text-muted-foreground">
              Rate {rupee(report.rate)}/day
            </span>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={downloadPdf}
            disabled={!report}
          >
            Download PDF
          </Button>
        </div>
      </div>

      {error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : loading && !report ? (
        <p className="py-4 text-sm text-muted-foreground">Loading…</p>
      ) : !report ? null : (
        <div className="space-y-6">
          {report.groups.map((g) => (
            <div key={g.key}>
              <h3 className="mb-2 text-sm font-semibold">
                {g.label}{" "}
                <span className="font-normal text-muted-foreground">
                  ({g.rows.length})
                </span>
              </h3>
              {g.rows.length === 0 ? (
                <p className="py-1 text-sm text-muted-foreground">
                  No patients in this group.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm tabular-nums">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Patient</th>
                        <th className="py-2 pr-4 text-right font-medium">Days</th>
                        <th className="py-2 pr-4 text-right font-medium">
                          Rate/day
                        </th>
                        <th className="py-2 text-right font-medium">Monthly</th>
                      </tr>
                    </thead>
                    <tbody>
                      {g.rows.map((r) => (
                        <tr
                          key={r.patientPk + r.name}
                          className="cursor-pointer border-b last:border-0 hover:bg-muted/50"
                          onClick={() => router.push(`/patients/${r.patientPk}`)}
                        >
                          <td className="py-1.5 pr-4">
                            {r.name}
                            <span className="block font-mono text-xs text-muted-foreground">
                              {r.patientCode}
                            </span>
                          </td>
                          <td className="py-1.5 pr-4 text-right">{r.days}</td>
                          <td className="py-1.5 pr-4 text-right">
                            {rupee(r.rate)}
                          </td>
                          <td className="py-1.5 text-right">{rupee(r.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 font-semibold">
                        <td className="py-2 pr-4">Group total</td>
                        <td className="py-2 pr-4 text-right">{g.totalDays}</td>
                        <td className="py-2 pr-4"></td>
                        <td className="py-2 text-right">
                          {rupee(g.totalAmount)}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}
            </div>
          ))}

          <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-4 py-3 text-sm font-semibold">
            <span>Grand total</span>
            <span>
              {report.grandTotalDays} patient-days &middot;{" "}
              <span className="text-primary">
                {rupee(report.grandTotalAmount)}
              </span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
