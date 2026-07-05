"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { Card } from "@/components/ui/card";
import { TableSkeleton, QueryError, EmptyState } from "@/components/query-states";
import { FEES_DUE_LIST } from "@/lib/graphql/operations";
import { formatINR } from "@/components/dashboard/format";

type Row = {
  id: string;
  patientId: string;
  name: string;
  room: string | null;
  dueDate: string;
  amountDue: string;
  daysUntilDue: number;
};

function dueBadge(days: number): string {
  if (days <= 0) return "bg-red-50 text-red-700";
  if (days <= 1) return "bg-amber-50 text-amber-700";
  return "bg-muted text-muted-foreground";
}
function dueLabel(days: number): string {
  if (days <= 0) return "Today";
  if (days === 1) return "1 day";
  return `${days} days`;
}

const TH = "text-[11.5px] font-medium uppercase tracking-wide";

export function FeesDueCard() {
  const router = useRouter();
  // Uses the existing feesDueList resolver.
  const { data, loading, error, refetch } = useQuery<{ feesDueList: Row[] }>(
    FEES_DUE_LIST,
    { variables: { withinDays: 7 } }
  );

  const rows = (data?.feesDueList ?? [])
    .slice()
    .sort((a, b) => a.daysUntilDue - b.daysUntilDue)
    .slice(0, 5);

  return (
    <Card className="overflow-hidden p-0 shadow-none">
      <div className="flex items-center justify-between px-[18px] pb-3 pt-4">
        <div>
          <div className="text-sm font-semibold">Fees due soon</div>
          <div className="mt-0.5 text-[12.5px] text-muted-foreground">Upcoming billing cycles</div>
        </div>
        <Link
          href="/fees-due"
          className="flex items-center gap-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground"
        >
          View all <ChevronRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {loading ? (
        <div className="px-[18px] pb-[18px]">
          <TableSkeleton rows={4} cols={4} />
        </div>
      ) : error ? (
        <div className="px-[18px] pb-[18px]">
          <QueryError message={error.message} onRetry={() => refetch()} />
        </div>
      ) : rows.length === 0 ? (
        <div className="px-[18px] pb-[18px]">
          <EmptyState title="No fees due" description="Nothing in the next 7 days." />
        </div>
      ) : (
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className={`px-[18px] py-2 ${TH}`}>Patient</th>
              <th className={`px-2.5 py-2 ${TH}`}>Room</th>
              <th className={`px-2.5 py-2 ${TH}`}>Due</th>
              <th className={`px-[18px] py-2 text-right ${TH}`}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.id}
                onClick={() => router.push(`/patients/${r.id}`)}
                className="cursor-pointer border-t hover:bg-muted/40"
              >
                <td className="px-[18px] py-2.5">
                  <div className="font-semibold">{r.name}</div>
                  <div className="font-mono text-[11px] text-muted-foreground">{r.patientId}</div>
                </td>
                <td className="px-2.5 py-2.5 text-muted-foreground">{r.room ?? "—"}</td>
                <td className="px-2.5 py-2.5">
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${dueBadge(
                      r.daysUntilDue
                    )}`}
                  >
                    {dueLabel(r.daysUntilDue)}
                  </span>
                </td>
                <td className="px-[18px] py-2.5 text-right font-semibold tabular-nums">
                  {formatINR(r.amountDue)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
