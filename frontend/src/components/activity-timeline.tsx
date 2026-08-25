"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/format-date";
import { ACTIVITIES, ADD_ACTIVITY } from "@/lib/graphql/operations";

type Activity = {
  id: string;
  type: string;
  body: string;
  outcome: string;
  createdAt: string;
  createdBy: { email: string } | null;
};
type Result = { activities: Activity[] };

const TYPE_LABEL: Record<string, string> = {
  NOTE: "Note",
  CALL: "Call",
  WHATSAPP: "WhatsApp",
  STAGE_CHANGE: "Stage",
  FOLLOW_UP: "Follow-up",
  SYSTEM: "System",
};

const TYPE_STYLE: Record<string, string> = {
  NOTE: "bg-zinc-100 text-zinc-600",
  CALL: "bg-blue-50 text-blue-700",
  WHATSAPP: "bg-green-50 text-green-700",
  STAGE_CHANGE: "bg-violet-50 text-violet-700",
  FOLLOW_UP: "bg-amber-50 text-amber-700",
  SYSTEM: "bg-zinc-100 text-zinc-500",
};

// Types a PRO can log by hand (system ones are written automatically).
const MANUAL_TYPES = ["NOTE", "CALL", "WHATSAPP"] as const;

/**
 * Interaction timeline for a lead (inquiryId) or a patient (patientId). PRO can
 * add notes; everyone allowed to see it reads. Pass exactly one id.
 */
export function ActivityTimeline({
  inquiryId,
  patientId,
  canAdd,
  refreshKey,
}: {
  inquiryId?: string;
  patientId?: string;
  canAdd: boolean;
  // Bump to re-fetch after an external event (e.g. a logged contact).
  refreshKey?: number;
}) {
  const variables = { inquiryId: inquiryId ?? null, patientId: patientId ?? null };
  const { data, loading, refetch } = useQuery<Result>(ACTIVITIES, {
    variables,
    fetchPolicy: "cache-and-network",
  });

  useEffect(() => {
    if (refreshKey !== undefined) refetch();
  }, [refreshKey, refetch]);

  const [type, setType] = useState<string>("NOTE");
  const [body, setBody] = useState("");
  const [add, { loading: adding }] = useMutation(ADD_ACTIVITY, {
    onCompleted: () => {
      setBody("");
      refetch();
    },
    onError: () => {},
  });

  const rows = data?.activities ?? [];

  function submit() {
    if (!body.trim()) return;
    add({ variables: { ...variables, type, body: body.trim(), outcome: null } });
  }

  return (
    <div className="space-y-4">
      {canAdd ? (
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Activity type"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            {MANUAL_TYPES.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABEL[t]}
              </option>
            ))}
          </select>
          <Input
            className="min-w-[160px] flex-1"
            placeholder="Log an interaction…"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
          <Button size="sm" onClick={submit} disabled={adding || !body.trim()}>
            Add
          </Button>
        </div>
      ) : null}

      {loading && rows.length === 0 ? (
        <p className="py-2 text-sm text-muted-foreground">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="py-2 text-sm text-muted-foreground">No activity yet.</p>
      ) : (
        <ol className="space-y-3">
          {rows.map((a) => (
            <li key={a.id} className="flex gap-3">
              <span
                className={`mt-0.5 h-fit whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                  TYPE_STYLE[a.type] ?? "bg-zinc-100 text-zinc-600"
                }`}
              >
                {TYPE_LABEL[a.type] ?? a.type}
              </span>
              <div className="min-w-0">
                <p className="text-sm">{a.body}</p>
                {a.outcome ? (
                  <p className="text-xs text-muted-foreground">{a.outcome}</p>
                ) : null}
                <p className="text-[11px] text-muted-foreground">
                  {formatDateTime(a.createdAt)}
                  {a.createdBy ? ` · ${a.createdBy.email.split("@")[0]}` : ""}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
