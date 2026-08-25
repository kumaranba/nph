"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ActivityTimeline } from "@/components/activity-timeline";
import { ConsentControl } from "@/components/consent-control";
import { ContactActions } from "@/components/contact-actions";
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
  ASSIGN_INQUIRY,
  INQUIRIES,
  PRO_USERS,
  UPDATE_INQUIRY_STATUS,
} from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type Inquiry = {
  id: string;
  name: string;
  phone: string;
  source: string;
  status: string;
  lostReason: string;
  contactConsent: string;
  doNotContact: boolean;
  notes: string;
  createdAt: string;
  assignedTo: { id: string; email: string } | null;
  patient: { id: string; patientId: string; name: string } | null;
};

type Result = { inquiries: Inquiry[] };
type ProUsers = { proUsers: Array<{ id: string; email: string }> };

const SOURCE_LABEL: Record<string, string> = {
  WHATSAPP: "WhatsApp",
  PHONE: "Phone",
  WALKIN: "Walk-in",
  WEB: "Web",
  REFERRAL: "Referral",
  OP_CONSULT: "OP consult",
  OP_IMPORT: "OP list",
};

// Pipeline stages (the backend field is `status`).
const STATUS_LABEL: Record<string, string> = {
  NEW: "New",
  CONTACTED: "Contacted",
  CONSULTED: "Consulted",
  ADMITTED: "Admitted",
  LOST: "Lost",
};

const STATUS_STYLE: Record<string, string> = {
  NEW: "bg-blue-50 text-blue-700",
  CONTACTED: "bg-amber-50 text-amber-700",
  CONSULTED: "bg-violet-50 text-violet-700",
  ADMITTED: "bg-green-50 text-green-700",
  LOST: "bg-zinc-100 text-zinc-600",
};

// Manually-settable stages (ADMITTED is reached only by linking a patient).
const MANUAL_STATUSES = ["NEW", "CONTACTED", "CONSULTED", "LOST"];

const LOST_REASONS: Array<{ value: string; label: string }> = [
  { value: "COST", label: "Cost" },
  { value: "DISTANCE", label: "Distance" },
  { value: "CHOSE_OTHER", label: "Chose another provider" },
  { value: "NOT_READY", label: "Not ready / declined" },
  { value: "UNREACHABLE", label: "Unreachable" },
  { value: "OTHER", label: "Other" },
];

export default function InquiriesPage() {
  const router = useRouter();
  const me = useMe();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [linkTarget, setLinkTarget] = useState<Inquiry | null>(null);
  const [lostTarget, setLostTarget] = useState<Inquiry | null>(null);
  const [historyTarget, setHistoryTarget] = useState<Inquiry | null>(null);
  const [histKey, setHistKey] = useState(0);

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
  const [assignInquiry] = useMutation(ASSIGN_INQUIRY, { onError: () => {} });

  const { data: proData } = useQuery<ProUsers>(PRO_USERS, {
    skip: !hasToken || !allowed,
  });
  const pros = proData?.proUsers ?? [];

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
                        {r.doNotContact ? (
                          <span className="ml-2 rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">
                            Do not contact
                          </span>
                        ) : null}
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
                        <button
                          type="button"
                          onClick={() => setHistoryTarget(r)}
                          className="mt-0.5 text-[11px] font-medium text-primary hover:underline"
                        >
                          History
                        </button>
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
                            Admitted →
                          </button>
                        ) : (
                          <span
                            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${
                              STATUS_STYLE[r.status] ?? "bg-zinc-100 text-zinc-600"
                            }`}
                            title={
                              r.status === "LOST" && r.lostReason
                                ? `Lost: ${r.lostReason}`
                                : undefined
                            }
                          >
                            {STATUS_LABEL[r.status] ?? r.status}
                          </span>
                        )}
                        {r.assignedTo ? (
                          <span className="mt-1 block text-[11px] text-muted-foreground">
                            {r.assignedTo.email.split("@")[0]}
                          </span>
                        ) : null}
                      </td>
                      <td className="py-2.5">
                        {canManage && r.status !== "ADMITTED" ? (
                          <div className="flex flex-wrap items-center gap-2">
                            <select
                              aria-label="Stage"
                              className="h-8 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              value={r.status}
                              onChange={async (e) => {
                                const next = e.target.value;
                                if (next === "LOST") {
                                  setLostTarget(r); // capture a reason first
                                  return;
                                }
                                await updateStatus({
                                  variables: { id: r.id, status: next },
                                });
                                if (statusFilter) refetch();
                              }}
                            >
                              {MANUAL_STATUSES.map((s) => (
                                <option key={s} value={s}>
                                  {STATUS_LABEL[s]}
                                </option>
                              ))}
                            </select>
                            {pros.length > 1 ? (
                              <select
                                aria-label="Owner"
                                className="h-8 max-w-[120px] rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                value={r.assignedTo?.id ?? ""}
                                onChange={(e) =>
                                  assignInquiry({
                                    variables: { id: r.id, userId: e.target.value },
                                  })
                                }
                              >
                                {r.assignedTo ? null : <option value="">—</option>}
                                {pros.map((p) => (
                                  <option key={p.id} value={p.id}>
                                    {p.email.split("@")[0]}
                                  </option>
                                ))}
                              </select>
                            ) : null}
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
      {lostTarget ? (
        <LostReasonModal
          inquiryName={lostTarget.name}
          onCancel={() => setLostTarget(null)}
          onConfirm={async (reason, note) => {
            await updateStatus({
              variables: {
                id: lostTarget.id,
                status: "LOST",
                lostReason: reason,
                lostReasonNote: note || null,
              },
            });
            setLostTarget(null);
            refetch();
          }}
        />
      ) : null}
      {historyTarget ? (
        <div
          className="fixed inset-0 z-50 flex justify-center bg-black/50 sm:items-center sm:p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Lead history"
          onClick={() => setHistoryTarget(null)}
        >
          <div
            className="flex h-full w-full flex-col bg-background shadow-lg sm:h-auto sm:max-h-[85vh] sm:max-w-md sm:rounded-lg sm:border"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b px-4 py-3.5">
              <div>
                <h2 className="text-base font-semibold">{historyTarget.name}</h2>
                <p className="text-xs text-muted-foreground">Interaction history</p>
              </div>
              <button
                type="button"
                aria-label="Close"
                onClick={() => setHistoryTarget(null)}
                className="rounded-md px-2 py-1 text-muted-foreground hover:bg-muted"
              >
                ✕
              </button>
            </div>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
              <ConsentControl
                inquiryId={historyTarget.id}
                consent={historyTarget.contactConsent}
                doNotContact={historyTarget.doNotContact}
                canEdit={canManage}
                onChanged={() => refetch()}
              />
              {canManage && historyTarget.phone ? (
                <ContactActions
                  phone={historyTarget.phone}
                  inquiryId={historyTarget.id}
                  consent={historyTarget.contactConsent}
                  doNotContact={historyTarget.doNotContact}
                  onLogged={() => setHistKey((k) => k + 1)}
                />
              ) : null}
              <ActivityTimeline
                inquiryId={historyTarget.id}
                canAdd={canManage}
                refreshKey={histKey}
              />
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

function LostReasonModal({
  inquiryName,
  onCancel,
  onConfirm,
}: {
  inquiryName: string;
  onCancel: () => void;
  onConfirm: (reason: string, note: string) => void;
}) {
  const [reason, setReason] = useState("COST");
  const [note, setNote] = useState("");
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Mark lead lost"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Mark lead lost</h2>
        <p className="mt-1 text-sm text-muted-foreground">{inquiryName}</p>
        <div className="mt-4 space-y-3">
          <div className="space-y-1.5">
            <label htmlFor="lost-reason" className="text-sm font-medium">
              Reason
            </label>
            <select
              id="lost-reason"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            >
              {LOST_REASONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="lost-note" className="text-sm font-medium">
              Note (optional)
            </label>
            <input
              id="lost-note"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Anything worth remembering"
            />
          </div>
        </div>
        <div className="mt-5 flex gap-2">
          <Button
            type="button"
            variant="outline"
            className="flex-1"
            onClick={onCancel}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            className="flex-1"
            onClick={() => onConfirm(reason, note)}
          >
            Mark lost
          </Button>
        </div>
      </div>
    </div>
  );
}
