"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  EmptyState,
  LinesSkeleton,
  QueryError,
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
  DUPLICATE_INQUIRY_GROUPS,
  MERGE_INQUIRIES,
} from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type Inquiry = {
  id: string;
  name: string;
  phone: string;
  source: string;
  status: string;
  consultedOn: string | null;
  createdAt: string;
  assignedTo: { id: string; email: string } | null;
  patient: { id: string; patientId: string; name: string } | null;
};
type Group = { key: string; inquiries: Inquiry[] };
type Result = { duplicateInquiryGroups: Group[] };

const SOURCE_LABEL: Record<string, string> = {
  WHATSAPP: "WhatsApp",
  PHONE: "Phone",
  WALKIN: "Walk-in",
  WEB: "Web",
  REFERRAL: "Referral",
  OP_CONSULT: "OP consult",
  OP_IMPORT: "OP list",
};
const STATUS_LABEL: Record<string, string> = {
  NEW: "New",
  CONTACTED: "Contacted",
  CONSULTED: "Consulted",
  ADMITTED: "Admitted",
  LOST: "Lost",
};

function groupLabel(key: string): string {
  if (key.startsWith("phone:")) return key.slice("phone:".length);
  if (key.startsWith("name:")) return `“${key.slice("name:".length)}”`;
  return key;
}

export default function DuplicatesPage() {
  const router = useRouter();
  const me = useMe();
  // Selected primary (survivor) per group key.
  const [primary, setPrimary] = useState<Record<string, string>>({});

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "PRO" || me?.role === "ADMIN";
  const canMerge = me?.role === "PRO"; // ADMIN is view-only

  const { data, loading, error, refetch } = useQuery<Result>(
    DUPLICATE_INQUIRY_GROUPS,
    {
      skip: !hasToken || !allowed,
      fetchPolicy: "cache-and-network",
    }
  );

  const [merge, { loading: merging, error: mergeError }] = useMutation(
    MERGE_INQUIRIES,
    { onCompleted: () => refetch(), onError: () => {} }
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
              Duplicate review is available to Patient Relations and Admin only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  const groups = data?.duplicateInquiryGroups ?? [];

  async function mergeGroup(group: Group) {
    const survivorId = primary[group.key] ?? group.inquiries[0].id;
    // Merge every other inquiry in the group into the survivor, sequentially.
    for (const inq of group.inquiries) {
      if (inq.id === survivorId) continue;
      await merge({
        variables: { primaryId: survivorId, duplicateId: inq.id },
      });
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl space-y-5 p-4 sm:p-6 lg:p-8">
      <Card>
        <CardHeader>
          <CardTitle>Duplicate inquiries</CardTitle>
          <CardDescription>
            Leads that look like the same person (matched by phone, or by name
            when there&apos;s no phone). Pick the record to keep, then merge —
            timeline, follow-ups, and details are combined into it.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && !data ? (
            <LinesSkeleton lines={4} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : groups.length === 0 ? (
            <EmptyState
              title="No duplicates found"
              description="Every inquiry looks unique right now."
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              {groups.length} group{groups.length === 1 ? "" : "s"} to review.
            </p>
          )}
        </CardContent>
      </Card>

      {mergeError ? (
        <p className="text-sm text-red-600">{mergeError.message}</p>
      ) : null}

      {groups.map((group) => {
        const survivorId = primary[group.key] ?? group.inquiries[0].id;
        return (
          <Card key={group.key}>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-base">
                  {groupLabel(group.key)}
                </CardTitle>
                <span className="text-xs text-muted-foreground">
                  {group.inquiries.length} records
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <ul className="space-y-2">
                {group.inquiries.map((inq) => {
                  const isSurvivor = inq.id === survivorId;
                  return (
                    <li
                      key={inq.id}
                      className={`flex items-start gap-3 rounded-lg border p-3 ${
                        isSurvivor ? "border-primary bg-primary/5" : ""
                      }`}
                    >
                      <input
                        type="radio"
                        name={`primary-${group.key}`}
                        className="mt-1"
                        checked={isSurvivor}
                        onChange={() =>
                          setPrimary((p) => ({ ...p, [group.key]: inq.id }))
                        }
                        disabled={!canMerge}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{inq.name}</span>
                          <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                            {SOURCE_LABEL[inq.source] ?? inq.source}
                          </span>
                          <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                            {STATUS_LABEL[inq.status] ?? inq.status}
                          </span>
                          {isSurvivor ? (
                            <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary">
                              Keep
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          {[
                            inq.phone,
                            `added ${formatDate(inq.createdAt)}`,
                            inq.assignedTo?.email.split("@")[0],
                            inq.patient
                              ? `patient ${inq.patient.patientId}`
                              : null,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
              {canMerge ? (
                <div className="flex justify-end">
                  <Button
                    size="sm"
                    onClick={() => mergeGroup(group)}
                    disabled={merging}
                  >
                    {merging ? "Merging…" : "Merge into kept record"}
                  </Button>
                </div>
              ) : null}
            </CardContent>
          </Card>
        );
      })}
    </main>
  );
}
