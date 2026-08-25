"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

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

const KIND_LABEL: Record<string, string> = {
  AFTERCARE: "Aftercare",
  OP_NUDGE: "OP nudge",
  MANUAL: "",
};

type Result = { dueFollowUps: DueFollowUp[] };

export default function FollowUpsPage() {
  const router = useRouter();
  const me = useMe();

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "PRO" || me?.role === "ADMIN";
  const canManage = me?.role === "PRO";

  const { data, loading, error, refetch } = useQuery<Result>(DUE_FOLLOW_UPS, {
    skip: !hasToken || !allowed,
    fetchPolicy: "cache-and-network",
  });

  const [markDone, { loading: marking }] = useMutation(MARK_FOLLOW_UP_DONE, {
    // Refresh the due list and the bell/badge count together.
    refetchQueries: [{ query: DUE_FOLLOW_UPS }, { query: DUE_FOLLOW_UP_COUNT }],
    onError: () => {},
  });

  const rows = data?.dueFollowUps ?? [];

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
          <CardTitle>Follow-ups due</CardTitle>
          <CardDescription>
            Reminders scheduled for today or earlier that aren’t done yet
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading && rows.length === 0 ? (
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
