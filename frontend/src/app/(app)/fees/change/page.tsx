"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { EmptyState, QueryError, TableSkeleton } from "@/components/query-states";
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
  CHANGE_FEE,
  FEE_HISTORY,
  ME,
  PATIENT,
  SEARCH_PATIENTS,
} from "@/lib/graphql/operations";
import { useDebounce } from "@/lib/use-debounce";

type SearchRow = { id: string; patientId: string; name: string };
type ActiveFee = { id: string; amount: string; effectiveFrom: string };
type Admission = {
  id: string;
  status: string;
  monthlyFee: string;
  nextFeeCycleDate: string;
  activeFee: ActiveFee | null;
};
type PatientResult = {
  patient: { id: string; name: string; admissions: Admission[] } | null;
};
type MeResult = { me: { role: string } };
type FeeRow = {
  id: string;
  amount: string;
  effectiveFrom: string;
  isActive: boolean;
  reason: string;
  createdAt: string;
  createdBy: { email: string } | null;
};
type HistoryResult = { feeHistory: FeeRow[] };

type ChangeForm = {
  amount: string;
  effectiveFrom: string;
  reason: string;
  override: boolean;
};

function money(v: string | number) {
  return `₹${Number(v).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function ChangeFeePage() {
  const router = useRouter();

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data: meData, loading: meLoading } = useQuery<MeResult>(ME, {
    skip: !hasToken,
  });
  const role = meData?.me.role ?? "";
  const canView = role === "ADMIN" || role === "FINANCE";
  const canChange = role === "FINANCE"; // ADMIN is view-only

  const [term, setTerm] = useState("");
  const [selected, setSelected] = useState<SearchRow | null>(null);
  const debounced = useDebounce(term, 300);

  const { data: searchData } = useQuery<{ searchPatients: SearchRow[] }>(
    SEARCH_PATIENTS,
    {
      variables: { query: debounced.trim() },
      skip: !canView || selected !== null || debounced.trim() === "",
    }
  );

  const { data: patientData, refetch: refetchPatient } =
    useQuery<PatientResult>(PATIENT, {
      variables: { pk: selected?.id },
      skip: !selected,
    });
  const admission = patientData?.patient?.admissions.find(
    (a) => a.status === "ACTIVE"
  );

  const {
    data: historyData,
    loading: historyLoading,
    error: historyError,
    refetch: refetchHistory,
  } = useQuery<HistoryResult>(FEE_HISTORY, {
    variables: { patientId: selected?.id },
    skip: !selected || !canView,
  });

  const { register, handleSubmit, watch, reset, setValue } =
    useForm<ChangeForm>({
      defaultValues: { amount: "", effectiveFrom: "", reason: "", override: false },
    });

  // Seed the effective-date field with the admission's default next cycle.
  useEffect(() => {
    if (admission) setValue("effectiveFrom", admission.nextFeeCycleDate);
  }, [admission, setValue]);

  const effectiveFrom = watch("effectiveFrom");
  const isCustomDate =
    !!admission && effectiveFrom !== admission.nextFeeCycleDate;

  const [changeFee, { loading: saving, error: mutationError }] = useMutation(
    CHANGE_FEE,
    {
      onCompleted: () => {
        reset({
          amount: "",
          effectiveFrom: admission?.nextFeeCycleDate ?? "",
          reason: "",
          override: false,
        });
        refetchPatient();
        refetchHistory();
      },
      onError: () => {},
    }
  );

  function onSubmit(values: ChangeForm) {
    if (!admission) return;
    changeFee({
      variables: {
        admissionId: admission.id,
        amount: values.amount,
        reason: values.reason,
        effectiveFrom: values.effectiveFrom || null,
        override: isCustomDate ? values.override : false,
      },
    });
  }

  if (!hasToken || meLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (!canView) {
    return (
      <main className="mx-auto min-h-screen max-w-2xl p-8">
        <Card>
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
            <CardDescription>
              Fee management is available to Admin and Finance only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-2xl space-y-5 p-6">
      <h1 className="text-xl font-semibold">Change fee</h1>

      {/* Patient picker */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Patient</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {selected ? (
            <div className="flex items-center justify-between">
              <div>
                <span className="font-medium">{selected.name}</span>{" "}
                <span className="font-mono text-xs text-muted-foreground">
                  {selected.patientId}
                </span>
                {admission ? (
                  <p className="text-sm text-muted-foreground">
                    Current fee{" "}
                    {admission.activeFee
                      ? `${money(admission.activeFee.amount)} (from ${
                          admission.activeFee.effectiveFrom
                        })`
                      : "—"}
                  </p>
                ) : (
                  <p className="text-sm text-red-600">
                    No active admission — fees can only be changed while admitted.
                  </p>
                )}
              </div>
              <Button
                variant="outline"
                onClick={() => {
                  setSelected(null);
                  reset();
                }}
              >
                Change
              </Button>
            </div>
          ) : (
            <>
              <Input
                type="search"
                autoFocus
                placeholder="Search patient by name…"
                value={term}
                onChange={(e) => setTerm(e.target.value)}
              />
              <ul className="divide-y">
                {(searchData?.searchPatients ?? []).map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className="w-full py-2 text-left hover:bg-muted/50"
                      onClick={() => {
                        setSelected(p);
                        setTerm("");
                      }}
                    >
                      {p.name}{" "}
                      <span className="font-mono text-xs text-muted-foreground">
                        {p.patientId}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>

      {/* Change form — Finance only, active admission only */}
      {selected && admission && canChange ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">New fee</CardTitle>
            <CardDescription>
              Takes effect from the next billing cycle by default. The current
              fee is retained in history.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="amount">New amount</Label>
                  <Input
                    id="amount"
                    type="number"
                    min={0}
                    step="0.01"
                    placeholder="0.00"
                    {...register("amount", { required: true })}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="effectiveFrom">Effective from</Label>
                  <Input
                    id="effectiveFrom"
                    type="date"
                    {...register("effectiveFrom", { required: true })}
                  />
                </div>
              </div>

              {isCustomDate ? (
                <label className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm">
                  <input type="checkbox" className="mt-0.5" {...register("override")} />
                  <span className="text-amber-800">
                    This differs from the default next billing cycle (
                    {admission.nextFeeCycleDate}). Confirm the override.
                  </span>
                </label>
              ) : null}

              <div className="space-y-1.5">
                <Label htmlFor="reason">Reason</Label>
                <Input
                  id="reason"
                  placeholder="e.g. Annual revision, room upgrade…"
                  {...register("reason", { required: true })}
                />
              </div>

              {mutationError ? (
                <p className="text-sm text-red-600">{mutationError.message}</p>
              ) : null}

              <Button
                type="submit"
                disabled={saving || (isCustomDate && !watch("override"))}
              >
                {saving ? "Saving…" : "Change fee"}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {/* Fee history */}
      {selected ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Fee history</CardTitle>
          </CardHeader>
          <CardContent>
            {historyLoading ? (
              <TableSkeleton rows={3} cols={4} />
            ) : historyError ? (
              <QueryError
                message={historyError.message}
                onRetry={() => refetchHistory()}
              />
            ) : (historyData?.feeHistory.length ?? 0) === 0 ? (
              <EmptyState title="No fee history" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Amount</th>
                      <th className="py-2 pr-4 font-medium">Effective</th>
                      <th className="py-2 pr-4 font-medium">Status</th>
                      <th className="py-2 pr-4 font-medium">Reason</th>
                      <th className="py-2 font-medium">By</th>
                    </tr>
                  </thead>
                  <tbody>
                    {historyData!.feeHistory.map((f) => (
                      <tr key={f.id} className="border-b last:border-0">
                        <td className="py-2 pr-4">{money(f.amount)}</td>
                        <td className="py-2 pr-4">{f.effectiveFrom}</td>
                        <td className="py-2 pr-4">
                          {f.isActive ? (
                            <span className="inline-flex rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
                              Active
                            </span>
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              Inactive
                            </span>
                          )}
                        </td>
                        <td className="py-2 pr-4 text-muted-foreground">
                          {f.reason || "—"}
                        </td>
                        <td className="py-2 text-xs text-muted-foreground">
                          {f.createdBy?.email ?? "system"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}
    </main>
  );
}
