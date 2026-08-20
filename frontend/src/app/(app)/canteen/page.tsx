"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { CanteenReport } from "@/components/canteen-report";
import { LinesSkeleton, QueryError } from "@/components/query-states";
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
import { formatDate } from "@/lib/format-date";
import { SET_STAFF_MEAL_RATE, STAFF_MEAL_RATES } from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type Rate = {
  id: string;
  amount: string;
  effectiveFrom: string;
  note: string;
  createdBy: { email: string } | null;
};
type Result = {
  currentStaffMealRate: { id: string; amount: string; effectiveFrom: string } | null;
  staffMealRates: Rate[];
};

type RateForm = { amount: string; effectiveFrom: string; note: string };

const rupee = (n: string | number) =>
  `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

const todayStr = () => new Date().toISOString().slice(0, 10);

export default function CanteenPage() {
  const router = useRouter();
  const me = useMe();
  const [showForm, setShowForm] = useState(false);
  const [tab, setTab] = useState<"report" | "rate">("report");

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "ADMIN" || me?.role === "FINANCE";

  const { data, loading, error, refetch } = useQuery<Result>(STAFF_MEAL_RATES, {
    skip: !hasToken || !allowed,
    fetchPolicy: "cache-and-network",
  });

  const { register, handleSubmit, reset } = useForm<RateForm>({
    defaultValues: { amount: "", effectiveFrom: todayStr(), note: "" },
  });

  const [setRate, { loading: saving, error: saveError }] = useMutation(
    SET_STAFF_MEAL_RATE,
    {
      onCompleted: () => {
        reset({ amount: "", effectiveFrom: todayStr(), note: "" });
        setShowForm(false);
        refetch();
      },
      onError: () => {},
    }
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
              The canteen is available to Admin and Finance only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  const current = data?.currentStaffMealRate ?? null;
  const rates = data?.staffMealRates ?? [];

  function onSubmit(values: RateForm) {
    setRate({
      variables: {
        amount: values.amount,
        effectiveFrom: values.effectiveFrom || null,
        note: values.note,
      },
    });
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="flex gap-1 rounded-lg border bg-muted/40 p-1 text-sm">
        {[
          { k: "report", label: "Meal count" },
          { k: "rate", label: "Staff rate" },
        ].map((t) => (
          <button
            key={t.k}
            type="button"
            onClick={() => setTab(t.k as typeof tab)}
            className={`flex-1 rounded-md px-3 py-1.5 font-medium transition-colors ${
              tab === t.k
                ? "bg-background shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "report" ? (
        <Card>
          <CardHeader>
            <CardTitle>Canteen meal count</CardTitle>
            <CardDescription>
              Daily patient &amp; staff meals for a month, with costs
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CanteenReport />
          </CardContent>
        </Card>
      ) : null}

      {tab === "rate" ? (
      <>
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>Staff meal rate</CardTitle>
              <CardDescription>
                Monthly canteen charge per active staff member
              </CardDescription>
            </div>
            {!showForm ? (
              <Button size="sm" onClick={() => setShowForm(true)}>
                Set rate
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {loading && !data ? (
            <LinesSkeleton lines={3} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : (
            <>
              <div className="rounded-lg border bg-muted/30 p-4">
                <div className="text-xs text-muted-foreground">Current rate</div>
                {current ? (
                  <>
                    <div className="text-3xl font-bold">
                      {rupee(current.amount)}
                      <span className="text-base font-normal text-muted-foreground">
                        {" "}
                        / staff · month
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Effective {formatDate(current.effectiveFrom)}
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-muted-foreground">
                    No rate set yet. Set one to price staff canteen meals.
                  </div>
                )}
              </div>

              {showForm ? (
                <form
                  onSubmit={handleSubmit(onSubmit)}
                  className="space-y-3 rounded-lg border p-4"
                >
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="sr-amount">Amount (₹ / staff · month)</Label>
                      <Input
                        id="sr-amount"
                        type="number"
                        min={0}
                        step="0.01"
                        placeholder="0.00"
                        {...register("amount", { required: true })}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="sr-eff">Effective from</Label>
                      <Input
                        id="sr-eff"
                        type="date"
                        {...register("effectiveFrom", { required: true })}
                      />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="sr-note">Note (optional)</Label>
                    <Input
                      id="sr-note"
                      placeholder="e.g. revised canteen rate"
                      {...register("note")}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Adds a new effective-dated rate — earlier rates are kept, so
                    past months stay priced correctly.
                  </p>
                  {saveError ? (
                    <p className="text-sm text-red-600">{saveError.message}</p>
                  ) : null}
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      className="flex-1"
                      onClick={() => {
                        reset();
                        setShowForm(false);
                      }}
                      disabled={saving}
                    >
                      Cancel
                    </Button>
                    <Button type="submit" className="flex-1" disabled={saving}>
                      {saving ? "Saving…" : "Save rate"}
                    </Button>
                  </div>
                </form>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rate history</CardTitle>
          <CardDescription>Every rate change, newest first</CardDescription>
        </CardHeader>
        <CardContent>
          {rates.length === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">
              No rates recorded yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Effective from</th>
                    <th className="py-2 pr-4 font-medium">Rate</th>
                    <th className="py-2 pr-4 font-medium">Note</th>
                    <th className="py-2 font-medium">Set by</th>
                  </tr>
                </thead>
                <tbody>
                  {rates.map((r) => (
                    <tr key={r.id} className="border-b last:border-0">
                      <td className="py-2 pr-4 whitespace-nowrap">
                        {formatDate(r.effectiveFrom)}
                        {current && r.id === current.id ? (
                          <span className="ml-2 rounded-full bg-green-50 px-1.5 text-[11px] font-semibold text-green-700">
                            current
                          </span>
                        ) : null}
                      </td>
                      <td className="py-2 pr-4 whitespace-nowrap font-medium">
                        {rupee(r.amount)}
                      </td>
                      <td className="py-2 pr-4">{r.note || "—"}</td>
                      <td className="py-2 text-muted-foreground">
                        {r.createdBy?.email ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      </>
      ) : null}
    </main>
  );
}
