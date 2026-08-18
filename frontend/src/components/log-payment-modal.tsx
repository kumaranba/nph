"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { INVOICE, LOG_PAYMENT, PAYMENT_ACCOUNTS } from "@/lib/graphql/operations";

type Account = { id: string; name: string };

type LogPaymentForm = {
  amount: string;
  paidOn: string;
  accountId: string;
};

type Props = {
  invoiceId: string;
  /** For refetching the invoice after the payment lands. */
  patientId: string;
  period: string;
  balanceDue: string;
  onClose: () => void;
};

export function LogPaymentModal({
  invoiceId,
  patientId,
  period,
  balanceDue,
  onClose,
}: Props) {
  const { register, handleSubmit } = useForm<LogPaymentForm>({
    defaultValues: {
      amount: "",
      paidOn: new Date().toISOString().slice(0, 10),
      accountId: "",
    },
  });

  const { data: accountsData } = useQuery<{ paymentAccounts: Account[] }>(
    PAYMENT_ACCOUNTS
  );
  const accounts = accountsData?.paymentAccounts ?? [];

  const [logPayment, { loading, error }] = useMutation(LOG_PAYMENT, {
    refetchQueries: [{ query: INVOICE, variables: { patientId, period } }],
    onCompleted: onClose,
    onError: () => {},
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function onSubmit(values: LogPaymentForm) {
    logPayment({
      variables: {
        invoiceId,
        amount: values.amount,
        paidOn: values.paidOn,
        accountId: values.accountId || null,
      },
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Log payment"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Log payment</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Balance due: {balanceDue}
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="amount">Amount</Label>
            <Input
              id="amount"
              type="number"
              min={0}
              step="0.01"
              placeholder="0.00"
              {...register("amount", { required: true })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="paidOn">Paid on</Label>
            <Input
              id="paidOn"
              type="date"
              {...register("paidOn", { required: true })}
            />
          </div>
          <div className="space-y-2">
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

          {error ? (
            <p className="text-sm text-red-600">{error.message}</p>
          ) : null}

          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" className="flex-1" disabled={loading}>
              {loading ? "Saving…" : "Record payment"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
