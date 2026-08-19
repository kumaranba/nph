"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ImportOpListModal } from "@/components/import-op-list-modal";
import { LinkInquiryModal } from "@/components/link-inquiry-modal";
import { NewInquiryModal } from "@/components/new-inquiry-modal";
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
  INQUIRIES,
  UPDATE_INQUIRY_STATUS,
} from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type Inquiry = {
  id: string;
  name: string;
  phone: string;
  source: string;
  status: string;
  notes: string;
  createdAt: string;
  patient: { id: string; patientId: string; name: string } | null;
};

type Result = { inquiries: Inquiry[] };

const SOURCE_LABEL: Record<string, string> = {
  WHATSAPP: "WhatsApp",
  PHONE: "Phone",
  WALKIN: "Walk-in",
  WEB: "Web",
  OP_IMPORT: "OP list",
};

const STATUS_LABEL: Record<string, string> = {
  NEW: "New",
  FOLLOWED_UP: "Followed up",
  CONVERTED: "Converted",
  CLOSED: "Closed",
};

const STATUS_STYLE: Record<string, string> = {
  NEW: "bg-blue-50 text-blue-700",
  FOLLOWED_UP: "bg-amber-50 text-amber-700",
  CONVERTED: "bg-green-50 text-green-700",
  CLOSED: "bg-zinc-100 text-zinc-600",
};

// Manually-settable statuses (CONVERTED is reached only by linking a patient).
const MANUAL_STATUSES = ["NEW", "FOLLOWED_UP", "CLOSED"];

export default function InquiriesPage() {
  const router = useRouter();
  const me = useMe();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [linkTarget, setLinkTarget] = useState<Inquiry | null>(null);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "PRO" || me?.role === "ADMIN";
  const canManage = me?.role === "PRO";

  const { data, loading, error, refetch } = useQuery<Result>(INQUIRIES, {
    variables: { status: statusFilter || null, search: search || null },
    skip: !hasToken || !allowed,
    fetchPolicy: "cache-and-network",
  });

  const [updateStatus] = useMutation(UPDATE_INQUIRY_STATUS, {
    onError: () => {},
  });

  const rows = data?.inquiries ?? [];

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
              Inquiries are available to Patient Relations and Admin only.
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
              <CardTitle>Inquiries</CardTitle>
              <CardDescription>
                Prospective-patient enquiries and their status
              </CardDescription>
            </div>
            {canManage ? (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowImport(true)}
                >
                  Import OP list
                </Button>
                <Button size="sm" onClick={() => setShowNew(true)}>
                  New inquiry
                </Button>
              </div>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <span className="text-sm font-medium text-muted-foreground">
                Status
              </span>
              <select
                className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">All statuses</option>
                {Object.entries(STATUS_LABEL).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-[200px] flex-1 space-y-1.5">
              <span className="text-sm font-medium text-muted-foreground">
                Search
              </span>
              <input
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Name or phone…"
              />
            </div>
          </div>

          {loading && rows.length === 0 ? (
            <TableSkeleton rows={5} cols={5} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No inquiries"
              description={
                statusFilter || search
                  ? "No inquiries match your filters."
                  : "No inquiries logged yet."
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 font-medium">Source</th>
                    <th className="py-2 pr-4 font-medium">Logged</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 font-medium">
                      {canManage ? "Actions" : ""}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-b last:border-0 align-top">
                      <td className="py-2.5 pr-4">
                        <span className="font-medium">{r.name}</span>
                        {r.phone ? (
                          <span className="block text-xs text-muted-foreground">
                            {r.phone}
                          </span>
                        ) : null}
                        {r.notes ? (
                          <span className="block max-w-[240px] truncate text-xs text-muted-foreground">
                            {r.notes}
                          </span>
                        ) : null}
                      </td>
                      <td className="py-2.5 pr-4 whitespace-nowrap">
                        {SOURCE_LABEL[r.source] ?? r.source}
                      </td>
                      <td className="py-2.5 pr-4 whitespace-nowrap">
                        {formatDate(r.createdAt)}
                      </td>
                      <td className="py-2.5 pr-4">
                        {r.patient ? (
                          <button
                            type="button"
                            onClick={() =>
                              router.push(`/patients/${r.patient!.id}`)
                            }
                            className="inline-flex items-center rounded-full bg-green-50 px-2 py-0.5 text-xs font-semibold text-green-700 hover:underline"
                            title={`${r.patient.name} · ${r.patient.patientId}`}
                          >
                            Converted →
                          </button>
                        ) : (
                          <span
                            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${
                              STATUS_STYLE[r.status] ?? "bg-zinc-100 text-zinc-600"
                            }`}
                          >
                            {STATUS_LABEL[r.status] ?? r.status}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5">
                        {canManage && r.status !== "CONVERTED" ? (
                          <div className="flex flex-wrap items-center gap-2">
                            <select
                              className="h-8 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              value={r.status}
                              onChange={async (e) => {
                                await updateStatus({
                                  variables: { id: r.id, status: e.target.value },
                                });
                                // Keep a status-filtered list consistent.
                                if (statusFilter) refetch();
                              }}
                            >
                              {MANUAL_STATUSES.map((s) => (
                                <option key={s} value={s}>
                                  {STATUS_LABEL[s]}
                                </option>
                              ))}
                            </select>
                            <button
                              type="button"
                              onClick={() => setLinkTarget(r)}
                              className="text-xs font-medium text-primary hover:underline"
                            >
                              Convert
                            </button>
                          </div>
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

      {showNew ? <NewInquiryModal onClose={() => setShowNew(false)} /> : null}
      {showImport ? (
        <ImportOpListModal
          onClose={() => setShowImport(false)}
          onImported={() => refetch()}
        />
      ) : null}
      {linkTarget ? (
        <LinkInquiryModal
          inquiryId={linkTarget.id}
          inquiryName={linkTarget.name}
          onClose={() => setLinkTarget(null)}
        />
      ) : null}
    </main>
  );
}
