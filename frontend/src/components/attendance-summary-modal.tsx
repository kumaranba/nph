"use client";

import { useQuery } from "@apollo/client";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ATTENDANCE_SUMMARY } from "@/lib/graphql/operations";

type Summary = {
  staff: { id: string; name: string; staffCode: string };
  present: number;
  absent: number;
  leave: number;
  halfDay: number;
  markedDays: number;
};

// First and last day of the month containing `d` (YYYY-MM-DD strings).
function monthBounds(d: Date) {
  const from = new Date(d.getFullYear(), d.getMonth(), 1);
  const to = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  const iso = (x: Date) =>
    `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(
      x.getDate()
    ).padStart(2, "0")}`;
  return { from: iso(from), to: iso(to) };
}

export function AttendanceSummaryModal({
  staffId,
  staffName,
  staffCode,
  onClose,
}: {
  staffId: string;
  staffName: string;
  staffCode: string;
  onClose: () => void;
}) {
  const init = monthBounds(new Date());
  const [from, setFrom] = useState(init.from);
  const [to, setTo] = useState(init.to);

  const { data, loading } = useQuery<{ attendanceSummary: Summary }>(
    ATTENDANCE_SUMMARY,
    { variables: { staffId, from, to }, fetchPolicy: "cache-and-network" }
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const s = data?.attendanceSummary;
  const tiles: Array<{ label: string; value: number; cls: string }> = [
    { label: "Present", value: s?.present ?? 0, cls: "text-green-700" },
    { label: "Absent", value: s?.absent ?? 0, cls: "text-red-700" },
    { label: "Leave", value: s?.leave ?? 0, cls: "text-amber-700" },
    { label: "Half-day", value: s?.halfDay ?? 0, cls: "text-blue-700" },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Attendance summary"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">{staffName}</h2>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{staffCode}</p>

        <div className="mt-4 flex items-end gap-2">
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="su-from">From</Label>
            <Input
              id="su-from"
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </div>
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="su-to">To</Label>
            <Input
              id="su-to"
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          {tiles.map((t) => (
            <div key={t.label} className="rounded-lg border p-3 text-center">
              <div className={`text-2xl font-bold ${t.cls}`}>{t.value}</div>
              <div className="text-xs text-muted-foreground">{t.label}</div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-center text-sm text-muted-foreground">
          {loading ? "Loading…" : `${s?.markedDays ?? 0} day(s) marked`}
        </p>

        <Button
          type="button"
          variant="outline"
          className="mt-5 w-full"
          onClick={onClose}
        >
          Close
        </Button>
      </div>
    </div>
  );
}
