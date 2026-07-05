"use client";

import { useQuery } from "@apollo/client";
import { BedDouble, Wallet, CalendarClock, AlertTriangle } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { DASHBOARD_STATS } from "@/lib/graphql/dashboard-operations";
import { formatLakh } from "@/components/dashboard/format";

type Stats = {
  bedsOccupied: number;
  bedsTotal: number;
  outstandingTotal: string;
  outstandingInvoiceCount: number;
  overdueCount: number;
  feesDueTotal: string;
  feesDueCount: number;
  feesDueToday: number;
  flaggedVitalsCount: number;
  flaggedPatientCount: number;
  criticalCount: number;
};

function Dot({ className }: { className: string }) {
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${className}`} />;
}

export function KpiCards() {
  const { data, loading } = useQuery<{ dashboardStats: Stats }>(DASHBOARD_STATS);
  const s = data?.dashboardStats;
  const occPct = s && s.bedsTotal ? Math.round((s.bedsOccupied / s.bedsTotal) * 100) : 0;
  const vacant = s ? s.bedsTotal - s.bedsOccupied : 0;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {/* Bed occupancy */}
      <Card className="p-[18px] shadow-none">
        <div className="flex items-start justify-between">
          <span className="text-[12.5px] font-medium text-muted-foreground">Bed occupancy</span>
          <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-muted">
            <BedDouble className="h-4 w-4 text-muted-foreground" />
          </span>
        </div>
        {loading ? (
          <Skeleton className="mt-3 h-8 w-28" />
        ) : (
          <>
            <div className="mt-3 text-[27px] font-semibold tabular-nums tracking-tight">
              {s?.bedsOccupied ?? "—"}
              <span className="text-base font-medium text-muted-foreground"> / {s?.bedsTotal ?? "—"}</span>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded bg-muted">
              <div className="h-full rounded bg-emerald-600" style={{ width: `${occPct}%` }} />
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              {vacant} vacant · <span className="font-semibold text-emerald-700">{occPct}% full</span>
            </div>
          </>
        )}
      </Card>

      {/* Outstanding balances */}
      <Card className="p-[18px] shadow-none">
        <div className="flex items-start justify-between">
          <span className="text-[12.5px] font-medium text-muted-foreground">Outstanding balances</span>
          <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-muted">
            <Wallet className="h-4 w-4 text-muted-foreground" />
          </span>
        </div>
        {loading ? (
          <Skeleton className="mt-3 h-8 w-28" />
        ) : (
          <>
            <div className="mt-3 text-[27px] font-semibold tabular-nums tracking-tight">
              {formatLakh(s?.outstandingTotal ?? 0)}
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
              <span>{s?.outstandingInvoiceCount ?? 0} invoices</span>
              <span className="h-[3px] w-[3px] rounded-full bg-border" />
              <span className="flex items-center gap-1.5 font-semibold text-red-600">
                <Dot className="bg-red-500" />
                {s?.overdueCount ?? 0} overdue
              </span>
            </div>
          </>
        )}
      </Card>

      {/* Fees due */}
      <Card className="p-[18px] shadow-none">
        <div className="flex items-start justify-between">
          <span className="text-[12.5px] font-medium text-muted-foreground">Fees due · next 7 days</span>
          <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-muted">
            <CalendarClock className="h-4 w-4 text-muted-foreground" />
          </span>
        </div>
        {loading ? (
          <Skeleton className="mt-3 h-8 w-28" />
        ) : (
          <>
            <div className="mt-3 text-[27px] font-semibold tabular-nums tracking-tight">
              {formatLakh(s?.feesDueTotal ?? 0)}
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5 font-semibold text-amber-700">
                <Dot className="bg-amber-500" />
                {s?.feesDueCount ?? 0} patients
              </span>
              <span className="h-[3px] w-[3px] rounded-full bg-border" />
              <span>{s?.feesDueToday ?? 0} due today</span>
            </div>
          </>
        )}
      </Card>

      {/* Flagged vitals */}
      <Card className="p-[18px] shadow-none">
        <div className="flex items-start justify-between">
          <span className="text-[12.5px] font-medium text-muted-foreground">Flagged vitals today</span>
          <span className="flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-red-50">
            <AlertTriangle className="h-4 w-4 text-red-600" />
          </span>
        </div>
        {loading ? (
          <Skeleton className="mt-3 h-8 w-16" />
        ) : (
          <>
            <div className="mt-3 text-[27px] font-semibold tabular-nums tracking-tight">
              {s?.flaggedVitalsCount ?? "—"}
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
              <span>across {s?.flaggedPatientCount ?? 0} patients</span>
              <span className="h-[3px] w-[3px] rounded-full bg-border" />
              <span className="font-semibold text-red-600">{s?.criticalCount ?? 0} critical</span>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
