"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { LinesSkeleton, QueryError } from "@/components/query-states";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getAccessToken } from "@/lib/auth";
import { INQUIRIES, UPDATE_INQUIRY_STATUS } from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type Inquiry = {
  id: string;
  name: string;
  phone: string;
  source: string;
  status: string;
  lostReason: string;
  consultedOn: string | null;
  createdAt: string;
  assignedTo: { id: string; email: string } | null;
  patient: { id: string; patientId: string; name: string } | null;
};
type Result = { inquiries: Inquiry[] };

const SOURCE_LABEL: Record<string, string> = {
  WHATSAPP: "WhatsApp",
  PHONE: "Phone",
  WALKIN: "Walk-in",
  WEB: "Web",
  REFERRAL: "Referral",
  OP_CONSULT: "OP consult",
  OP_IMPORT: "OP list",
};

const LOST_REASONS: Array<{ value: string; label: string }> = [
  { value: "COST", label: "Cost" },
  { value: "DISTANCE", label: "Distance" },
  { value: "CHOSE_OTHER", label: "Chose another provider" },
  { value: "NOT_READY", label: "Not ready / declined" },
  { value: "UNREACHABLE", label: "Unreachable" },
  { value: "OTHER", label: "Other" },
];

// Columns, in pipeline order. NEW/CONTACTED/CONSULTED are the working stages a
// card can be freely moved between; LOST is a valid target (with a reason);
// ADMITTED is terminal and reached only by converting to a patient elsewhere.
const COLUMNS: Array<{
  key: string;
  label: string;
  head: string;
  droppable: boolean;
}> = [
  { key: "NEW", label: "New", head: "bg-blue-50 text-blue-700", droppable: true },
  { key: "CONTACTED", label: "Contacted", head: "bg-amber-50 text-amber-700", droppable: true },
  { key: "CONSULTED", label: "Consulted", head: "bg-violet-50 text-violet-700", droppable: true },
  { key: "ADMITTED", label: "Admitted", head: "bg-green-50 text-green-700", droppable: false },
  { key: "LOST", label: "Lost", head: "bg-red-50 text-red-700", droppable: true },
];

function ageLabel(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  return `${days}d`;
}

export default function PipelinePage() {
  const router = useRouter();
  const me = useMe();
  const [dragId, setDragId] = useState<string | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);
  // The card whose tap-to-move menu is open.
  const [menuId, setMenuId] = useState<string | null>(null);
  // Pending move to LOST awaiting a reason: { id, name }.
  const [lostTarget, setLostTarget] = useState<Inquiry | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "PRO" || me?.role === "ADMIN";
  const canMove = me?.role === "PRO";

  const { data, loading, error, refetch } = useQuery<Result>(INQUIRIES, {
    variables: { status: null, search: null },
    skip: !hasToken || !allowed,
    fetchPolicy: "cache-and-network",
  });

  const [updateStatus, { loading: moving }] = useMutation(
    UPDATE_INQUIRY_STATUS,
    { onCompleted: () => refetch(), onError: (e) => setNotice(e.message) }
  );

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
              The pipeline board is available to Patient Relations and Admin
              only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  const inquiries = data?.inquiries ?? [];
  const byStage = (stage: string) =>
    inquiries.filter((i) => i.status === stage);

  function move(inq: Inquiry, target: string) {
    setMenuId(null);
    setDragId(null);
    setOverCol(null);
    if (inq.status === target) return;
    if (target === "ADMITTED") {
      setNotice("To admit a lead, convert it to a patient from the Inquiries list.");
      return;
    }
    if (target === "LOST") {
      setLostTarget(inq);
      return;
    }
    setNotice(null);
    updateStatus({ variables: { id: inq.id, status: target } });
  }

  function confirmLost(reason: string, note: string) {
    if (!lostTarget) return;
    updateStatus({
      variables: {
        id: lostTarget.id,
        status: "LOST",
        lostReason: reason,
        lostReasonNote: note || null,
      },
    });
    setLostTarget(null);
  }

  return (
    <main className="mx-auto min-h-screen max-w-6xl space-y-4 p-4 sm:p-6 lg:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Pipeline</h1>
          <p className="text-sm text-muted-foreground">
            {canMove
              ? "Drag a card, or tap Move, to change its stage."
              : "Inquiry pipeline (read-only)."}
          </p>
        </div>
      </div>

      {notice ? (
        <div className="flex items-center justify-between gap-3 rounded-lg border bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <span>{notice}</span>
          <button
            className="text-xs underline"
            onClick={() => setNotice(null)}
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {loading && !data ? (
        <LinesSkeleton lines={6} />
      ) : error ? (
        <QueryError message={error.message} onRetry={() => refetch()} />
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {COLUMNS.map((col) => {
            const cards = byStage(col.key);
            const isDropTarget =
              canMove && col.droppable && dragId !== null;
            return (
              <div
                key={col.key}
                className={`flex w-64 shrink-0 flex-col rounded-lg border bg-muted/20 ${
                  overCol === col.key && isDropTarget
                    ? "ring-2 ring-primary"
                    : ""
                }`}
                onDragOver={(e) => {
                  if (!isDropTarget) return;
                  e.preventDefault();
                  setOverCol(col.key);
                }}
                onDragLeave={() => setOverCol((c) => (c === col.key ? null : c))}
                onDrop={(e) => {
                  e.preventDefault();
                  if (!canMove || !col.droppable) return;
                  const inq = inquiries.find((i) => i.id === dragId);
                  if (inq) move(inq, col.key);
                }}
              >
                <div
                  className={`flex items-center justify-between rounded-t-lg px-3 py-2 text-sm font-medium ${col.head}`}
                >
                  <span>{col.label}</span>
                  <span className="tabular-nums">{cards.length}</span>
                </div>
                <div className="flex-1 space-y-2 p-2">
                  {cards.length === 0 ? (
                    <p className="px-1 py-6 text-center text-xs text-muted-foreground">
                      —
                    </p>
                  ) : (
                    cards.map((inq) => (
                      <PipelineCard
                        key={inq.id}
                        inq={inq}
                        canMove={canMove}
                        moving={moving}
                        menuOpen={menuId === inq.id}
                        onToggleMenu={() =>
                          setMenuId((m) => (m === inq.id ? null : inq.id))
                        }
                        onDragStart={() => setDragId(inq.id)}
                        onDragEnd={() => {
                          setDragId(null);
                          setOverCol(null);
                        }}
                        onMove={(target) => move(inq, target)}
                      />
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {lostTarget ? (
        <LostReasonDialog
          name={lostTarget.name}
          onCancel={() => setLostTarget(null)}
          onConfirm={confirmLost}
        />
      ) : null}
    </main>
  );
}

function PipelineCard({
  inq,
  canMove,
  moving,
  menuOpen,
  onToggleMenu,
  onDragStart,
  onDragEnd,
  onMove,
}: {
  inq: Inquiry;
  canMove: boolean;
  moving: boolean;
  menuOpen: boolean;
  onToggleMenu: () => void;
  onDragStart: () => void;
  onDragEnd: () => void;
  onMove: (target: string) => void;
}) {
  const terminal = inq.status === "ADMITTED";
  // Move targets: the other working stages plus Lost (never Admitted).
  const targets = COLUMNS.filter(
    (c) => c.droppable && c.key !== inq.status
  );
  return (
    <div
      draggable={canMove && !terminal}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className={`rounded-md border bg-background p-2.5 text-sm shadow-sm ${
        canMove && !terminal ? "cursor-grab active:cursor-grabbing" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium leading-tight">{inq.name}</span>
        <span className="shrink-0 text-[11px] text-muted-foreground">
          {ageLabel(inq.createdAt)}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
          {SOURCE_LABEL[inq.source] ?? inq.source}
        </span>
        {inq.phone ? (
          <span className="text-[11px] text-muted-foreground">{inq.phone}</span>
        ) : null}
      </div>
      {inq.patient ? (
        <div className="mt-1 text-[11px] text-green-700">
          Patient {inq.patient.patientId}
        </div>
      ) : null}
      {inq.status === "LOST" && inq.lostReason ? (
        <div className="mt-1 text-[11px] text-red-600">
          Lost: {inq.lostReason}
        </div>
      ) : null}
      {inq.assignedTo ? (
        <div className="mt-1 text-[11px] text-muted-foreground">
          {inq.assignedTo.email.split("@")[0]}
        </div>
      ) : null}

      {canMove && !terminal ? (
        <div className="relative mt-2">
          <Button
            size="sm"
            variant="outline"
            className="h-7 w-full text-xs"
            onClick={onToggleMenu}
            disabled={moving}
          >
            Move ▾
          </Button>
          {menuOpen ? (
            <div className="absolute left-0 right-0 z-10 mt-1 overflow-hidden rounded-md border bg-background shadow-md">
              {targets.map((t) => (
                <button
                  key={t.key}
                  className="block w-full px-3 py-1.5 text-left text-xs hover:bg-muted"
                  onClick={() => onMove(t.key)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function LostReasonDialog({
  name,
  onCancel,
  onConfirm,
}: {
  name: string;
  onCancel: () => void;
  onConfirm: (reason: string, note: string) => void;
}) {
  const [reason, setReason] = useState(LOST_REASONS[0].value);
  const [note, setNote] = useState("");
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onCancel}
    >
      <Card className="w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
        <CardHeader>
          <CardTitle className="text-base">Mark “{name}” lost</CardTitle>
          <CardDescription>Why didn&apos;t this lead convert?</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <select
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          >
            {LOST_REASONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          <input
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            placeholder="Note (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => onConfirm(reason, note)}>
              Mark lost
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
