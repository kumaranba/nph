"use client";

import { useQuery } from "@apollo/client";
import { useState } from "react";

import { QueryError } from "@/components/query-states";
import { Button } from "@/components/ui/button";
import { getAccessToken } from "@/lib/auth";
import { formatDate } from "@/lib/format-date";
import { CANTEEN_REPORT } from "@/lib/graphql/operations";

const API_ORIGIN = (
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/"
).replace(/\/graphql\/?$/, "");

type Day = {
  day: string;
  dow: string;
  isSplit: boolean;
  malePatients: number;
  malePatientsNonveg: number;
  femalePatients: number;
  femalePatientsNonveg: number;
  otherPatients: number;
  otherPatientsNonveg: number;
  maleStaff: number;
  femaleStaff: number;
  otherStaff: number;
  total: number;
};
type Totals = {
  malePatients: number;
  femalePatients: number;
  otherPatients: number;
  maleStaff: number;
  femaleStaff: number;
  otherStaff: number;
  patientDays: number;
  staffDays: number;
  total: number;
};
type Result = {
  canteenReport: {
    month: string;
    dailyRate: string;
    staffMonthlyRate: string;
    activeStaff: number;
    hasOther: boolean;
    patientCost: string;
    staffCost: string;
    grandTotalCost: string;
    totals: Totals;
    days: Day[];
  };
};

const rupee = (n: string | number) =>
  `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

const currentMonth = () => new Date().toISOString().slice(0, 7);

// A patient cell: the total, with a small Veg/Non-veg split on split days.
function PatientCell({
  total,
  nonveg,
  isSplit,
}: {
  total: number;
  nonveg: number;
  isSplit: boolean;
}) {
  return (
    <span>
      {total}
      {isSplit && nonveg > 0 ? (
        <span className="block text-[10px] text-muted-foreground">
          {total - nonveg}V / {nonveg}N
        </span>
      ) : null}
    </span>
  );
}

export function CanteenReport() {
  const [month, setMonth] = useState(currentMonth());

  const { data, loading, error, refetch } = useQuery<Result>(CANTEEN_REPORT, {
    variables: { month },
    fetchPolicy: "cache-and-network",
  });

  const r = data?.canteenReport;
  const showOther = r?.hasOther ?? false;

  async function downloadPdf() {
    const token = getAccessToken();
    if (!token) return;
    const qs = new URLSearchParams({ month });
    const resp = await fetch(`${API_ORIGIN}/reports/canteen.pdf?${qs}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `canteen-${month}.pdf`;
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
        <Button variant="outline" size="sm" onClick={downloadPdf} disabled={!r}>
          Download PDF
        </Button>
      </div>

      {error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : loading && !r ? (
        <p className="py-4 text-sm text-muted-foreground">Loading…</p>
      ) : !r ? null : r.days.length === 0 ? (
        <p className="py-4 text-sm text-muted-foreground">
          No days to show for this month yet.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="py-2 pr-3 text-left font-medium" rowSpan={2}>
                    Date
                  </th>
                  <th
                    className="py-1 text-center font-medium text-green-700"
                    colSpan={showOther ? 3 : 2}
                  >
                    Patients
                  </th>
                  <th
                    className="py-1 text-center font-medium text-amber-700"
                    colSpan={showOther ? 3 : 2}
                  >
                    Staff
                  </th>
                  <th className="py-2 text-right font-medium" rowSpan={2}>
                    Total
                  </th>
                </tr>
                <tr className="border-b text-muted-foreground">
                  <th className="py-1 pr-3 text-right font-medium">M</th>
                  <th className="py-1 pr-3 text-right font-medium">F</th>
                  {showOther ? (
                    <th className="py-1 pr-3 text-right font-medium">O</th>
                  ) : null}
                  <th className="py-1 pr-3 text-right font-medium">M</th>
                  <th className="py-1 pr-3 text-right font-medium">F</th>
                  {showOther ? (
                    <th className="py-1 pr-3 text-right font-medium">O</th>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {r.days.map((d) => (
                  <tr
                    key={d.day}
                    className={`border-b last:border-0 ${
                      d.isSplit ? "bg-amber-50/40" : ""
                    }`}
                  >
                    <td className="py-1.5 pr-3 whitespace-nowrap">
                      {formatDate(d.day)}{" "}
                      <span className="text-xs text-muted-foreground">
                        {d.dow}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3 text-right">
                      <PatientCell
                        total={d.malePatients}
                        nonveg={d.malePatientsNonveg}
                        isSplit={d.isSplit}
                      />
                    </td>
                    <td className="py-1.5 pr-3 text-right">
                      <PatientCell
                        total={d.femalePatients}
                        nonveg={d.femalePatientsNonveg}
                        isSplit={d.isSplit}
                      />
                    </td>
                    {showOther ? (
                      <td className="py-1.5 pr-3 text-right">
                        <PatientCell
                          total={d.otherPatients}
                          nonveg={d.otherPatientsNonveg}
                          isSplit={d.isSplit}
                        />
                      </td>
                    ) : null}
                    <td className="py-1.5 pr-3 text-right">{d.maleStaff}</td>
                    <td className="py-1.5 pr-3 text-right">{d.femaleStaff}</td>
                    {showOther ? (
                      <td className="py-1.5 pr-3 text-right">{d.otherStaff}</td>
                    ) : null}
                    <td className="py-1.5 text-right font-medium">{d.total}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 font-semibold">
                  <td className="py-2 pr-3">Month total</td>
                  <td className="py-2 pr-3 text-right">
                    {r.totals.malePatients}
                  </td>
                  <td className="py-2 pr-3 text-right">
                    {r.totals.femalePatients}
                  </td>
                  {showOther ? (
                    <td className="py-2 pr-3 text-right">
                      {r.totals.otherPatients}
                    </td>
                  ) : null}
                  <td className="py-2 pr-3 text-right">{r.totals.maleStaff}</td>
                  <td className="py-2 pr-3 text-right">
                    {r.totals.femaleStaff}
                  </td>
                  {showOther ? (
                    <td className="py-2 pr-3 text-right">
                      {r.totals.otherStaff}
                    </td>
                  ) : null}
                  <td className="py-2 text-right">{r.totals.total}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="text-xs text-muted-foreground">
            Wed &amp; Sun serve both menus — patient cells show{" "}
            <b>Veg / Non-veg</b>; other days are Veg only. Staff is a single
            count.
          </p>

          {/* Cost summary */}
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="rounded-lg border p-3">
              <div className="text-xs text-muted-foreground">Patient meals</div>
              <div className="text-lg font-bold text-green-700">
                {rupee(r.patientCost)}
              </div>
              <div className="text-[11px] text-muted-foreground">
                {r.totals.patientDays} patient-days × {rupee(r.dailyRate)}/day
              </div>
            </div>
            <div className="rounded-lg border p-3">
              <div className="text-xs text-muted-foreground">Staff meals</div>
              <div className="text-lg font-bold text-amber-700">
                {rupee(r.staffCost)}
              </div>
              <div className="text-[11px] text-muted-foreground">
                {r.activeStaff} active staff × {rupee(r.staffMonthlyRate)}/mo
              </div>
            </div>
            <div className="rounded-lg border border-primary p-3">
              <div className="text-xs text-muted-foreground">Grand total</div>
              <div className="text-lg font-bold text-primary">
                {rupee(r.grandTotalCost)}
              </div>
              <div className="text-[11px] text-muted-foreground">
                patient + staff
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
