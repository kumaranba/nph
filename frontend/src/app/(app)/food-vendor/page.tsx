"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

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
import { FOOD_RATES, SET_FOOD_RATE } from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type Rate = {
  id: string;
  amount: string;
  effectiveFrom: string;
  note: string;
  createdBy: { email: string } | null;
};
type Result = {
  currentFoodRate: { id: string; amount: string; effectiveFrom: string } | null;
  foodRates: Rate[];
};

type RateForm = { amount: string; effectiveFrom: string; note: string };

const rupee = (n: string | number) =>
  `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

const todayStr = () => new Date().toISOString().slice(0, 10);

export default function FoodVendorPage() {
  const router = useRouter();
  const me = useMe();
  const [showForm, setShowForm] = useState(false);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "ADMIN" || me?.role === "FINANCE";

  const { data, loading, error, refetch } = useQuery<Result>(FOOD_RATES, {
    skip: !hasToken || !allowed,
    fetchPolicy: "cache-and-network",
  });

  const { register, handleSubmit, reset } = useForm<RateForm>({
    defaultValues: { amount: "", effectiveFrom: todayStr(), note: "" },
  });

  const [setRate, { loading: saving, error: saveError }] = useMutation(
    SET_FOOD_RATE,
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
              The food vendor rate is available to Admin and Finance only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  const current = data?.currentFoodRate ?? null;
  const rates = data?.foodRates ?? [];

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
    <main className="mx-auto min-h-screen max-w-3xl space-y-6 p-4 sm:p-6 lg:p-8">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>Food vendor rate</CardTitle>
              <CardDescription>
                Flat charge per patient-day paid to the caterer
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
                        / patient-day
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Effective {formatDate(current.effectiveFrom)}
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-muted-foreground">
                    No rate set yet. Set one to start the payment list.
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
                      <Label htmlFor="fr-amount">Amount (₹ / patient-day)</Label>
                      <Input
                        id="fr-amount"
                        type="number"
                        min={0}
                        step="0.01"
                        placeholder="0.00"
                        {...register("amount", { required: true })}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="fr-eff">Effective from</Label>
                      <Input
                        id="fr-eff"
                        type="date"
                        {...register("effectiveFrom", { required: true })}
                      />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="fr-note">Note (optional)</Label>
                    <Input
                      id="fr-note"
                      placeholder="e.g. renegotiated contract"
                      {...register("note")}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Adds a new effective-dated rate — earlier rates are kept, so
                    past periods stay priced correctly.
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
    </main>
  );
}
