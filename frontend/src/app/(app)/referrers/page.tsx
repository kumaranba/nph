"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getAccessToken } from "@/lib/auth";
import {
  CREATE_REFERRER,
  REFERRERS,
  REFERRER_STATS,
  UPDATE_REFERRER,
} from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type Referrer = {
  id: string;
  name: string;
  kind: string;
  organization: string;
  phone: string;
  email: string;
  notes: string;
  isActive: boolean;
};
type ReferrersResult = { referrers: Referrer[] };
type Stat = {
  referrer: { id: string; name: string; kind: string; organization: string };
  leads: number;
  converted: number;
  conversionRate: number;
};
type StatsResult = { referrerStats: Stat[] };

const KIND_LABEL: Record<string, string> = {
  DOCTOR: "Doctor",
  HOSPITAL: "Hospital / clinic",
  EX_PATIENT: "Former patient / family",
  STAFF: "Staff",
  OTHER: "Other",
};
const KINDS = Object.keys(KIND_LABEL);

const pct = (n: number) => `${Math.round(n * 100)}%`;

type RefForm = {
  name: string;
  kind: string;
  organization: string;
  phone: string;
  email: string;
  notes: string;
};

const EMPTY: RefForm = {
  name: "",
  kind: "DOCTOR",
  organization: "",
  phone: "",
  email: "",
  notes: "",
};

export default function ReferrersPage() {
  const router = useRouter();
  const me = useMe();
  // null = form closed; "" = adding new; an id = editing that referrer.
  const [editing, setEditing] = useState<string | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "PRO" || me?.role === "ADMIN";
  const canEdit = me?.role === "PRO"; // ADMIN is view-only

  const { data, loading, error, refetch } = useQuery<ReferrersResult>(
    REFERRERS,
    {
      variables: { includeInactive: showInactive },
      skip: !hasToken || !allowed,
      fetchPolicy: "cache-and-network",
    }
  );
  const { data: statsData, refetch: refetchStats } = useQuery<StatsResult>(
    REFERRER_STATS,
    { skip: !hasToken || !allowed, fetchPolicy: "cache-and-network" }
  );

  const { register, handleSubmit, reset } = useForm<RefForm>({
    defaultValues: EMPTY,
  });

  const refreshAll = () => {
    refetch();
    refetchStats();
  };

  const [createReferrer, { loading: creating, error: createError }] =
    useMutation(CREATE_REFERRER, {
      onCompleted: () => {
        setEditing(null);
        reset(EMPTY);
        refreshAll();
      },
      onError: () => {},
    });
  const [updateReferrer, { loading: updating, error: updateError }] =
    useMutation(UPDATE_REFERRER, {
      onCompleted: () => {
        setEditing(null);
        reset(EMPTY);
        refreshAll();
      },
      onError: () => {},
    });

  const saving = creating || updating;
  const saveError = createError || updateError;

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
              Referrers are available to Patient Relations and Admin only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  const referrers = data?.referrers ?? [];
  const stats = statsData?.referrerStats ?? [];
  const maxLeads = Math.max(1, ...stats.map((s) => s.leads));

  function openAdd() {
    reset(EMPTY);
    setEditing("");
  }
  function openEdit(r: Referrer) {
    reset({
      name: r.name,
      kind: r.kind,
      organization: r.organization,
      phone: r.phone,
      email: r.email,
      notes: r.notes,
    });
    setEditing(r.id);
  }

  function onSubmit(values: RefForm) {
    if (editing === "") {
      createReferrer({ variables: { data: values } });
    } else if (editing) {
      updateReferrer({ variables: { id: editing, data: values } });
    }
  }

  function toggleActive(r: Referrer) {
    updateReferrer({
      variables: { id: r.id, data: { isActive: !r.isActive } },
    });
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl space-y-5 p-4 sm:p-6 lg:p-8">
      {/* Leaderboard */}
      <Card>
        <CardHeader>
          <CardTitle>Top referrers</CardTitle>
          <CardDescription>Leads and conversions by source</CardDescription>
        </CardHeader>
        <CardContent>
          {stats.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No referred leads yet.
            </p>
          ) : (
            <div className="space-y-2.5">
              {stats.map((s) => (
                <div key={s.referrer.id}>
                  <div className="flex justify-between text-sm">
                    <span className="truncate">
                      {s.referrer.name}
                      {s.referrer.organization ? (
                        <span className="text-muted-foreground">
                          {" "}
                          · {s.referrer.organization}
                        </span>
                      ) : null}
                    </span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      {s.converted}/{s.leads} ·{" "}
                      <span className="font-medium text-foreground">
                        {pct(s.conversionRate)}
                      </span>
                    </span>
                  </div>
                  <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full bg-primary/70"
                      style={{ width: `${(s.leads / maxLeads) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Directory */}
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Referral sources</CardTitle>
              <CardDescription>
                Doctors, hospitals, and others who send patients
              </CardDescription>
            </div>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={showInactive}
                  onChange={(e) => setShowInactive(e.target.checked)}
                />
                Show inactive
              </label>
              {canEdit && editing === null ? (
                <Button size="sm" onClick={openAdd}>
                  Add referrer
                </Button>
              ) : null}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {editing !== null ? (
            <form
              onSubmit={handleSubmit(onSubmit)}
              className="space-y-3 rounded-lg border p-4"
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="rf-name">Name</Label>
                  <Input
                    id="rf-name"
                    placeholder="Dr. Rao"
                    {...register("name", { required: true })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rf-kind">Kind</Label>
                  <select
                    id="rf-kind"
                    className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    {...register("kind")}
                  >
                    {KINDS.map((k) => (
                      <option key={k} value={k}>
                        {KIND_LABEL[k]}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rf-org">Organization (optional)</Label>
                  <Input
                    id="rf-org"
                    placeholder="City Hospital"
                    {...register("organization")}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rf-phone">Phone (optional)</Label>
                  <Input id="rf-phone" {...register("phone")} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rf-email">Email (optional)</Label>
                  <Input id="rf-email" type="email" {...register("email")} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="rf-notes">Notes (optional)</Label>
                <Input id="rf-notes" {...register("notes")} />
              </div>
              {saveError ? (
                <p className="text-sm text-red-600">{saveError.message}</p>
              ) : null}
              <div className="flex gap-2">
                <Button type="submit" size="sm" disabled={saving}>
                  {saving
                    ? "Saving…"
                    : editing === ""
                      ? "Add referrer"
                      : "Save changes"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setEditing(null);
                    reset(EMPTY);
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          ) : null}

          {loading && !data ? (
            <LinesSkeleton lines={4} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : referrers.length === 0 ? (
            <EmptyState title="No referral sources yet." />
          ) : (
            <ul className="divide-y">
              {referrers.map((r) => (
                <li
                  key={r.id}
                  className="flex flex-wrap items-center justify-between gap-2 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{r.name}</span>
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                        {KIND_LABEL[r.kind] ?? r.kind}
                      </span>
                      {!r.isActive ? (
                        <span className="rounded bg-red-50 px-1.5 py-0.5 text-[11px] text-red-600">
                          Inactive
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {[r.organization, r.phone, r.email]
                        .filter(Boolean)
                        .join(" · ") || "—"}
                    </div>
                  </div>
                  {canEdit ? (
                    <div className="flex shrink-0 gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openEdit(r)}
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => toggleActive(r)}
                        disabled={saving}
                      >
                        {r.isActive ? "Deactivate" : "Reactivate"}
                      </Button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
