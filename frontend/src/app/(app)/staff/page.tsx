"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  EmptyState,
  QueryError,
  TableSkeleton,
} from "@/components/query-states";
import {
  DESIGNATIONS,
  StaffFormModal,
  type StaffRow,
} from "@/components/staff-form-modal";
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
import { STAFF_LIST } from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type Result = { staffList: StaffRow[] };

const DESIGNATION_LABEL: Record<string, string> = Object.fromEntries(
  DESIGNATIONS.map((d) => [d.value, d.label])
);

export default function StaffPage() {
  const router = useRouter();
  const me = useMe();
  const [search, setSearch] = useState("");
  const [designation, setDesignation] = useState("");
  const [includeInactive, setIncludeInactive] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<StaffRow | null>(null);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "ADMIN";

  const { data, loading, error, refetch } = useQuery<Result>(STAFF_LIST, {
    variables: {
      includeInactive,
      designation: designation || null,
      search: search || null,
    },
    skip: !hasToken || !allowed,
    fetchPolicy: "cache-and-network",
  });

  const rows = data?.staffList ?? [];

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
              The staff registry is available to Admin only.
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
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>Staff</CardTitle>
              <CardDescription>
                Employees on the premises — the basis for attendance
              </CardDescription>
            </div>
            <Button size="sm" onClick={() => setShowAdd(true)}>
              Add staff
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[200px] flex-1 space-y-1.5">
              <span className="text-sm font-medium text-muted-foreground">
                Search
              </span>
              <input
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Name, code or phone…"
              />
            </div>
            <div className="space-y-1.5">
              <span className="text-sm font-medium text-muted-foreground">
                Designation
              </span>
              <select
                className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={designation}
                onChange={(e) => setDesignation(e.target.value)}
              >
                <option value="">All</option>
                {DESIGNATIONS.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex h-9 items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={includeInactive}
                onChange={(e) => setIncludeInactive(e.target.checked)}
              />
              Show inactive
            </label>
          </div>

          {loading && rows.length === 0 ? (
            <TableSkeleton rows={5} cols={4} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No staff"
              description={
                search || designation
                  ? "No staff match your filters."
                  : "No staff added yet."
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Staff</th>
                    <th className="py-2 pr-4 font-medium">Designation</th>
                    <th className="py-2 pr-4 font-medium">Phone</th>
                    <th className="py-2 pr-4 font-medium">Joined</th>
                    <th className="py-2 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={r.id}
                      className={`border-b last:border-0 ${
                        r.isActive ? "" : "opacity-60"
                      }`}
                    >
                      <td className="py-2.5 pr-4">
                        <span className="font-medium">{r.name}</span>
                        <span className="block font-mono text-xs text-muted-foreground">
                          {r.staffCode}
                          {r.isActive ? "" : " · inactive"}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4">
                        {DESIGNATION_LABEL[r.designation] ?? r.designation}
                        <span className="block text-xs text-muted-foreground">
                          {r.gender
                            ? r.gender.charAt(0) + r.gender.slice(1).toLowerCase()
                            : "gender not set"}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 whitespace-nowrap">
                        {r.phone || "—"}
                      </td>
                      <td className="py-2.5 pr-4 whitespace-nowrap">
                        {r.joinedOn ? formatDate(r.joinedOn) : "—"}
                      </td>
                      <td className="py-2.5">
                        <button
                          type="button"
                          onClick={() => setEditing(r)}
                          className="text-xs font-medium text-primary hover:underline"
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {showAdd ? (
        <StaffFormModal
          onClose={() => setShowAdd(false)}
          onSaved={() => refetch()}
        />
      ) : null}
      {editing ? (
        <StaffFormModal
          staff={editing}
          onClose={() => setEditing(null)}
          onSaved={() => refetch()}
        />
      ) : null}
    </main>
  );
}
