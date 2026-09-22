"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  EmptyState,
  QueryError,
  TableSkeleton,
} from "@/components/query-states";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getAccessToken } from "@/lib/auth";
import { formatDate } from "@/lib/format-date";
import {
  COMPLETED_FOLLOW_UPS,
  DUE_FOLLOW_UP_COUNT,
  DUE_FOLLOW_UPS,
  MARK_FOLLOW_UP_DONE,
} from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type DueFollowUp = {
  id: string;
  note: string;
  followUpDate: string;
  kind: string;
  subjectName: string;
  patient: { id: string; patientId: string; name: string } | null;
  inquiry: { id: string; name: string } | null;
};

type CompletedFollowUp = DueFollowUp & { completedOn: string | null };

const KIND_LABEL: Record<string, string> = {
  AFTERCARE: "Aftercare",
  OP_NUDGE: "OP nudge",
  MANUAL: "",
};

type Result = { dueFollowUps: DueFollowUp[] };
type CompletedResult = { completedFollowUps: CompletedFollowUp[] };

export default function FollowUpsPage() {
  const router = useRouter();
  const me = useMe();
  const [tab, setTab] = useState<"due" | "completed">("due");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "PRO" || me?.role === "ADMIN";
  const canManage = me?.role === "PRO";

  const { data, loading, error, refetch } = useQuery<Result>(DUE_FOLLOW_UPS, {
    skip: !hasToken || !allowed || tab !== "due",
    fetchPolicy: "cache-and-network",
  });

  const completed = useQuery<CompletedResult>(COMPLETED_FOLLOW_UPS, {
    variables: { completedFrom: from || null, completedTo: to || null },
    skip: !hasToken || !allowed || tab !== "completed",
    fetchPolicy: "cache-and-network",
  });

  const [markDone, { loading: marking }] = useMutation(MARK_FOLLOW_UP_DONE, {
    // Refresh the due list and the bell/badge count together.
    refetchQueries: [{ query: DUE_FOLLOW_UPS }, { query: DUE_FOLLOW_UP_COUNT }],
    onError: () => {},
  });

  const rows = data?.dueFollowUps ?? [];
  const completedRows = completed.data?.completedFollowUps ?? [];

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
              Follow-ups are available to Patient Relations and Admin only.
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
          <div className="flex gap-1 border-b">
            <button
              type="button"
              onClick={() => setTab("due")}
              className={`-mb-px border-b-2 px-1 pb-2 text-sm font-medium ${
                tab === "due"
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Follow-ups due
            </button>
            <button
              type="button"
              onClick={() => setTab("completed")}
              className={`-mb-px ml-4 border-b-2 px-1 pb-2 text-sm font-medium ${
                tab === "completed"
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Completed
            </button>
          </div>
          <CardDescription className="pt-3">
            {tab === "due"
              ? "Reminders scheduled for today or earlier that aren’t done yet"
              : "Follow-ups already completed, filterable by completion date"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {tab === "completed" ? (
            <CompletedView
              rows={completedRows}
              loading={completed.loading}
              error={completed.error?.message}
              onRetry={() => completed.refetch()}
              from={from}
              to={to}
              setFrom={setFrom}
              setTo={setTo}
              onOpen={(r) =>
                router.push(r.patient ? `/patients/${r.patient.id}` : "/inquiries")
              }
            />
          ) : loading && rows.length === 0 ? (
            <TableSkeleton rows={5} cols={4} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : rows.length === 0 ? (
            <EmptyState
              title="All caught up"
              description="No follow-ups are due right now."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Who</th>
                    <th className="py-2 pr-4 font-medium">Due</th>
                    <th className="py-2 pr-4 font-medium">Note</th>
                    <th className="py-2 font-medium">
                      {canManage ? "Action" : ""}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-b last:border-0 align-top">
                      <td className="py-2.5 pr-4">
                        <button
                          type="button"
                          onClick={() =>
                            router.push(
                              r.patient
                                ? `/patients/${r.patient.id}`
                                : "/inquiries"
                            )
                          }
                          className="text-left font-medium hover:underline"
                        >
                          {r.subjectName}
                        </button>
                        <span className="block text-xs text-muted-foreground">
                          {r.patient ? (
                            <span className="font-mono">{r.patient.patientId}</span>
                          ) : (
                            "Lead"
                          )}
                          {KIND_LABEL[r.kind] ? ` · ${KIND_LABEL[r.kind]}` : ""}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 whitespace-nowrap">
                        {formatDate(r.followUpDate)}
                      </td>
                      <td className="py-2.5 pr-4">
                        {r.note || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-2.5">
                        {canManage ? (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={marking}
                            onClick={() =>
                              markDone({ variables: { id: r.id } })
                            }
                          >
                            Mark done
                          </Button>
                        ) : null}
                      </td>
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

function CompletedView({
  rows,
  loading,
  error,
  onRetry,
  from,
  to,
  setFrom,
  setTo,
  onOpen,
}: {
  rows: CompletedFollowUp[];
  loading: boolean;
  error?: string;
  onRetry: () => void;
  from: string;
  to: string;
  setFrom: (v: string) => void;
  setTo: (v: string) => void;
  onOpen: (r: CompletedFollowUp) => void;
}) {
  return (
    <>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <span className="text-sm font-medium text-muted-foreground">
            Completed from
          </span>
          <input
            type="date"
            className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={from}
            max={to || undefined}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <span className="text-sm font-medium text-muted-foreground">to</span>
          <input
            type="date"
            className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={to}
            min={from || undefined}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
        {from || to ? (
          <button
            type="button"
            className="h-9 text-xs font-medium text-muted-foreground hover:text-foreground"
            onClick={() => {
              setFrom("");
              setTo("");
            }}
          >
            Clear
          </button>
        ) : null}
      </div>

      {loading && rows.length === 0 ? (
        <TableSkeleton rows={5} cols={4} />
      ) : error ? (
        <QueryError message={error} onRetry={onRetry} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No completed follow-ups"
          description={
            from || to
              ? "None completed in this date range."
              : "No follow-ups have been completed yet."
          }
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-4 font-medium">Who</th>
                <th className="py-2 pr-4 font-medium">Completed</th>
                <th className="py-2 pr-4 font-medium">Scheduled</th>
                <th className="py-2 font-medium">Note</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b last:border-0 align-top">
                  <td className="py-2.5 pr-4">
                    <button
                      type="button"
                      onClick={() => onOpen(r)}
                      className="text-left font-medium hover:underline"
                    >
                      {r.subjectName}
                    </button>
                    <span className="block text-xs text-muted-foreground">
                      {r.patient ? (
                        <span className="font-mono">{r.patient.patientId}</span>
                      ) : (
                        "Lead"
                      )}
                      {KIND_LABEL[r.kind] ? ` · ${KIND_LABEL[r.kind]}` : ""}
                    </span>
                  </td>
                  <td className="py-2.5 pr-4 whitespace-nowrap">
                    {r.completedOn ? formatDate(r.completedOn) : "—"}
                  </td>
                  <td className="py-2.5 pr-4 whitespace-nowrap">
                    {formatDate(r.followUpDate)}
                  </td>
                  <td className="py-2.5">
                    {r.note || <span className="text-muted-foreground">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
