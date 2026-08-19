"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AttendanceSummaryModal } from "@/components/attendance-summary-modal";
import {
  EmptyState,
  QueryError,
  TableSkeleton,
} from "@/components/query-states";
import { DESIGNATIONS } from "@/components/staff-form-modal";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getAccessToken } from "@/lib/auth";
import {
  ATTENDANCE_ROSTER,
  BULK_MARK_ATTENDANCE,
} from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type RosterItem = {
  staff: { id: string; staffCode: string; name: string; designation: string };
  status: string | null;
};
type Result = { attendanceRoster: RosterItem[] };

const DESIGNATION_LABEL: Record<string, string> = Object.fromEntries(
  DESIGNATIONS.map((d) => [d.value, d.label])
);

const STATUS_OPTIONS = [
  { value: "PRESENT", label: "Present" },
  { value: "ABSENT", label: "Absent" },
  { value: "LEAVE", label: "Leave" },
  { value: "HALF_DAY", label: "Half-day" },
];

const todayStr = () => new Date().toISOString().slice(0, 10);

export default function AttendancePage() {
  const router = useRouter();
  const me = useMe();
  const [date, setDate] = useState(todayStr());
  // Local edits keyed by staff id ("" = unset).
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [summaryFor, setSummaryFor] = useState<RosterItem["staff"] | null>(null);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "ADMIN";

  const { data, loading, error, refetch } = useQuery<Result>(ATTENDANCE_ROSTER, {
    variables: { date },
    skip: !hasToken || !allowed,
    fetchPolicy: "cache-and-network",
    onCompleted: (d) => {
      const next: Record<string, string> = {};
      for (const r of d.attendanceRoster) next[r.staff.id] = r.status ?? "";
      setStatuses(next);
      setSaved(false);
    },
  });

  const [bulkMark, { loading: saving }] = useMutation(BULK_MARK_ATTENDANCE, {
    onCompleted: () => setSaved(true),
    onError: () => {},
  });

  const rows = useMemo(
    () => data?.attendanceRoster ?? [],
    [data?.attendanceRoster]
  );

  // Live tally of the current (edited) statuses for the selected date.
  const tally = useMemo(() => {
    const t = { PRESENT: 0, ABSENT: 0, LEAVE: 0, HALF_DAY: 0, unset: 0 };
    for (const r of rows) {
      const s = statuses[r.staff.id] ?? "";
      if (s === "") t.unset += 1;
      else t[s as keyof typeof t] += 1;
    }
    return t;
  }, [rows, statuses]);

  function setStatus(staffId: string, value: string) {
    setStatuses((prev) => ({ ...prev, [staffId]: value }));
    setSaved(false);
  }

  function markAllPresent() {
    const next: Record<string, string> = {};
    for (const r of rows) next[r.staff.id] = "PRESENT";
    setStatuses(next);
    setSaved(false);
  }

  function save() {
    const entries = rows
      .map((r) => ({ staffId: r.staff.id, status: statuses[r.staff.id] ?? "" }))
      .filter((e) => e.status !== "");
    if (entries.length === 0) return;
    bulkMark({ variables: { date, entries } }).then(() => refetch());
  }

  if (!hasToken) {
    return (
      <main className="flex min-h-screen items-center justify-center p-4">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (me && !allowed) {
    return (
      <main className="mx-auto min-h-screen max-w-3xl p-4 sm:p-6 lg:p-8">
        <Card>
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
            <CardDescription>
              Attendance is available to Admin only.
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
          <CardTitle>Attendance</CardTitle>
          <CardDescription>Mark the daily roster for staff</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="space-y-1.5">
              <span className="text-sm font-medium text-muted-foreground">
                Date
              </span>
              <input
                type="date"
                max={todayStr()}
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <span className="text-green-700">Present {tally.PRESENT}</span>
              <span className="text-red-700">Absent {tally.ABSENT}</span>
              <span className="text-amber-700">Leave {tally.LEAVE}</span>
              <span className="text-blue-700">Half {tally.HALF_DAY}</span>
              {tally.unset > 0 ? <span>Unmarked {tally.unset}</span> : null}
            </div>
          </div>

          {loading && rows.length === 0 ? (
            <TableSkeleton rows={6} cols={3} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No active staff"
              description="Add staff first, then mark attendance here."
            />
          ) : (
            <>
              <div className="flex items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={markAllPresent}
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Mark all present
                </button>
                {saved ? (
                  <span className="text-xs font-medium text-green-700">
                    Saved ✓
                  </span>
                ) : null}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Staff</th>
                      <th className="py-2 pr-4 font-medium">Designation</th>
                      <th className="py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.staff.id} className="border-b last:border-0">
                        <td className="py-2 pr-4">
                          <button
                            type="button"
                            onClick={() => setSummaryFor(r.staff)}
                            className="text-left font-medium hover:underline"
                          >
                            {r.staff.name}
                          </button>
                          <span className="block font-mono text-xs text-muted-foreground">
                            {r.staff.staffCode}
                          </span>
                        </td>
                        <td className="py-2 pr-4">
                          {DESIGNATION_LABEL[r.staff.designation] ??
                            r.staff.designation}
                        </td>
                        <td className="py-2">
                          <select
                            value={statuses[r.staff.id] ?? ""}
                            onChange={(e) => setStatus(r.staff.id, e.target.value)}
                            className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <option value="">— not marked —</option>
                            {STATUS_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Button className="w-full" onClick={save} disabled={saving}>
                {saving ? "Saving…" : "Save roster"}
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      {summaryFor ? (
        <AttendanceSummaryModal
          staffId={summaryFor.id}
          staffName={summaryFor.name}
          staffCode={summaryFor.staffCode}
          onClose={() => setSummaryFor(null)}
        />
      ) : null}
    </main>
  );
}
