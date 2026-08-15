"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";

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
  ME,
  PATIENT,
  PAYMENT_ACCOUNTS,
  RECORD_PATIENT_PAYMENT,
  SEARCH_PATIENTS,
} from "@/lib/graphql/operations";
import { useDebounce } from "@/lib/use-debounce";

type SearchRow = { id: string; patientId: string; name: string };
type Account = { id: string; name: string };
type Admission = {
  id: string;
  status: string;
  monthlyFee: string;
  creditBalance: string;
};
type PatientResult = {
  patient: { id: string; name: string; admissions: Admission[] } | null;
};
type MeResult = { me: { role: string } };
type RecordResult = {
  recordPatientPayment: {
    totalRecorded: string;
    feesAmount: string;
    chargesAmount: string;
    account: string | null;
    invoicesPaid: number;
    creditAdded: string;
    creditBalance: string;
    allocations: { period: string; amount: string }[];
  };
};

type PayForm = {
  feesAmount: string;
  chargesAmount: string;
  accountId: string;
  paidOn: string;
};

function money(v: string | number) {
  return `₹${Number(v).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function RecordPaymentPage() {
  return (
    <Suspense fallback={null}>
      <RecordPaymentForm />
    </Suspense>
  );
}

function RecordPaymentForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data: meData, loading: meLoading } = useQuery<MeResult>(ME, {
    skip: !hasToken,
  });
  const allowed =
    meData?.me.role === "ADMIN" || meData?.me.role === "FINANCE";

  const [term, setTerm] = useState("");
  const [selected, setSelected] = useState<SearchRow | null>(null);
  const debounced = useDebounce(term, 300);

  // Preselect a patient when arriving from the profile "Record payment" button
  // (/payments/new?id=..&name=..&code=..).
  useEffect(() => {
    const id = searchParams.get("id");
    if (id && !selected) {
      setSelected({
        id,
        name: searchParams.get("name") ?? "",
        patientId: searchParams.get("code") ?? "",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const { data: accountsData } = useQuery<{ paymentAccounts: Account[] }>(
    PAYMENT_ACCOUNTS,
    { skip: !allowed }
  );
  const accounts = accountsData?.paymentAccounts ?? [];

  const { data: searchData } = useQuery<{ searchPatients: SearchRow[] }>(
    SEARCH_PATIENTS,
    {
      variables: { query: debounced.trim() },
      skip: !allowed || selected !== null || debounced.trim() === "",
    }
  );

  const { data: patientData } = useQuery<PatientResult>(PATIENT, {
    variables: { pk: selected?.id },
    skip: !selected,
  });
  const admission = patientData?.patient?.admissions.find(
    (a) => a.status === "ACTIVE"
  );
  const monthlyFee = admission ? Number(admission.monthlyFee) : 0;

  const { register, handleSubmit, watch, reset } = useForm<PayForm>({
    defaultValues: {
      feesAmount: "",
      chargesAmount: "",
      accountId: "",
      paidOn: new Date().toISOString().slice(0, 10),
    },
  });
  const total = (Number(watch("feesAmount")) || 0) + (Number(watch("chargesAmount")) || 0);
  const monthsPreview = monthlyFee > 0 && total > 0 ? total / monthlyFee : 0;

  const [record, { data, loading, error }] = useMutation<RecordResult>(
    RECORD_PATIENT_PAYMENT,
    { onError: () => {} }
  );
  const result = data?.recordPatientPayment;

  function onSubmit(values: PayForm) {
    if (!selected) return;
    record({
      variables: {
        patientId: selected.id,
        feesAmount: values.feesAmount || "0",
        chargesAmount: values.chargesAmount || "0",
        accountId: values.accountId || null,
        paidOn: values.paidOn,
      },
    });
  }

  if (!hasToken || meLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-4 sm:p-6 lg:p-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (!allowed) {
    return (
      <main className="mx-auto min-h-screen max-w-2xl p-4 sm:p-6 lg:p-8">
        <Card>
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
            <CardDescription>
              Recording payments is available to Admin and Finance only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-lg space-y-5 p-4 sm:p-6">
      <h1 className="text-xl font-semibold">Record payment</h1>

      {/* Patient picker */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Patient</CardTitle>
          <CardDescription>
            Payments clear outstanding invoices first; any surplus is held as
            advance credit and applied automatically as future months are billed.
          </CardDescription>
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
                    Monthly fee {money(monthlyFee)}
                    {Number(admission.creditBalance) > 0
                      ? ` · Advance credit ${money(admission.creditBalance)}`
                      : ""}
                  </p>
                ) : (
                  <p className="text-sm text-red-600">
                    No active admission for this patient.
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

      {/* Payment form */}
      {selected && admission && !result ? (
        <Card>
          <CardContent className="pt-6">
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="feesAmount">Fees payment</Label>
                  <Input
                    id="feesAmount"
                    type="number"
                    min={0}
                    step="0.01"
                    placeholder="0.00"
                    {...register("feesAmount")}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="chargesAmount">Additional charges</Label>
                  <Input
                    id="chargesAmount"
                    type="number"
                    min={0}
                    step="0.01"
                    placeholder="0.00"
                    {...register("chargesAmount")}
                  />
                </div>
              </div>
              <div className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2 text-sm">
                <span className="text-muted-foreground">Total</span>
                <span className="font-semibold">{money(total)}</span>
              </div>
              {monthsPreview > 0 ? (
                <p className="text-xs text-muted-foreground">
                  ≈ {monthsPreview.toFixed(1)} month
                  {monthsPreview >= 2 ? "s" : ""} at {money(monthlyFee)}/mo
                </p>
              ) : null}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="accountId">Payment done at</Label>
                  <select
                    id="accountId"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    defaultValue=""
                    {...register("accountId", { required: true })}
                  >
                    <option value="" disabled>
                      Select account
                    </option>
                    {accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="paidOn">Paid on</Label>
                  <Input
                    id="paidOn"
                    type="date"
                    {...register("paidOn", { required: true })}
                  />
                </div>
              </div>

              {error ? (
                <p className="text-sm text-red-600">{error.message}</p>
              ) : null}

              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Recording…" : "Record payment"}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {/* Result summary */}
      {result ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-green-700">
              Payment recorded
            </CardTitle>
            <CardDescription>
              {money(result.totalRecorded)} recorded
              {result.account ? ` at ${result.account}` : ""} ·{" "}
              {result.invoicesPaid} invoice
              {result.invoicesPaid === 1 ? "" : "s"} cleared
              {Number(result.creditAdded) > 0
                ? ` · ${money(result.creditAdded)} added to advance credit`
                : ""}
              <br />
              Fees {money(result.feesAmount)} · Additional charges{" "}
              {money(result.chargesAmount)}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {result.allocations.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 font-medium">Billing month</th>
                    <th className="py-2 text-right font-medium">Applied</th>
                  </tr>
                </thead>
                <tbody>
                  {result.allocations.map((a) => (
                    <tr key={a.period} className="border-b last:border-0">
                      <td className="py-2">{a.period}</td>
                      <td className="py-2 text-right">{money(a.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            <p className="text-sm">
              Advance credit balance:{" "}
              <span className="font-medium">{money(result.creditBalance)}</span>
              {Number(result.creditBalance) > 0 ? (
                <span className="text-muted-foreground">
                  {" "}
                  — applied automatically as upcoming months are billed.
                </span>
              ) : null}
            </p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => router.push("/fees-due")}>
                Back to fees due
              </Button>
              <Button
                onClick={() => {
                  setSelected(null);
                  reset();
                }}
              >
                Record another
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </main>
  );
}
