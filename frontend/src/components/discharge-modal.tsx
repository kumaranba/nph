"use client";

import { useMutation, useQuery } from "@apollo/client";
import { Lock } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatDate } from "@/lib/format-date";
import {
  DISCHARGE_PATIENT,
  DISCHARGE_PREVIEW,
  PATIENT,
  PAYMENT_ACCOUNTS,
} from "@/lib/graphql/operations";

type Line = { label: string; kind: string; amount: string };
type Preview = {
  dischargePreview: {
    dischargeDate: string;
    hasCurrentCycle: boolean;
    cycleStart: string | null;
    cycleEnd: string | null;
    fullFee: string;
    daysInPeriod: number;
    daysStayed: number;
    proratedFee: string;
    cancelledFee: string;
    feesDue: string;
    chargesDue: string;
    totalDueNow: string;
    lines: Line[];
  };
};
type Accounts = { paymentAccounts: Array<{ id: string; name: string }> };

const rupee = (n: string | number) =>
  `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const todayStr = () => new Date().toISOString().slice(0, 10);

type Props = {
  admissionId: string;
  patientId: string;
  patientName: string;
  /** Current user's role; only Finance sees the refund field. */
  role: string;
  onClose: () => void;
};

export function DischargeModal({
  admissionId,
  patientId,
  patientName,
  role,
  onClose,
}: Props) {
  const isFinance = role === "FINANCE";

  const [dischargeDate, setDischargeDate] = useState(todayStr());
  const [feesPaid, setFeesPaid] = useState("");
  const [chargesPaid, setChargesPaid] = useState("");
  const [accountId, setAccountId] = useState("");
  const [refundAmount, setRefundAmount] = useState("");
  const [prefilled, setPrefilled] = useState(false);

  const { data, loading: previewing, error: previewError } = useQuery<Preview>(
    DISCHARGE_PREVIEW,
    {
      variables: { admissionId, dischargeDate },
      fetchPolicy: "cache-and-network",
      onCompleted: (d) => {
        if (!prefilled && d?.dischargePreview) {
          setFeesPaid(d.dischargePreview.feesDue);
          setChargesPaid(d.dischargePreview.chargesDue);
          setPrefilled(true);
        }
      },
    }
  );
  const { data: acctData } = useQuery<Accounts>(PAYMENT_ACCOUNTS);

  const [discharge, { data: done, loading, error }] = useMutation(
    DISCHARGE_PATIENT,
    {
      refetchQueries: [{ query: PATIENT, variables: { pk: patientId } }],
      onError: () => {},
    }
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const pv = data?.dischargePreview;
  const isDone = Boolean(done?.dischargePatient);
  const totalDue = pv ? Number(pv.totalDueNow) : 0;
  const paying = (Number(feesPaid) || 0) + (Number(chargesPaid) || 0);
  const shortfall = Math.round((totalDue - paying) * 100) / 100;
  const tallied = pv != null && shortfall <= 0.005;
  const payPct = totalDue > 0 ? Math.min(100, (paying / totalDue) * 100) : 100;
  const stayPct =
    pv && pv.daysInPeriod > 0 ? (pv.daysStayed / pv.daysInPeriod) * 100 : 0;

  function confirm() {
    discharge({
      variables: {
        admissionId,
        dischargeDate,
        feesPaid: feesPaid || "0",
        chargesPaid: chargesPaid || "0",
        accountId: accountId || null,
        refundAmount: isFinance && refundAmount !== "" ? refundAmount : null,
      },
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-center bg-black/50 sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Discharge patient"
      onClick={onClose}
    >
      <div
        className="flex h-full w-full flex-col bg-background shadow-lg sm:h-auto sm:max-h-[90vh] sm:max-w-lg sm:rounded-lg sm:border"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b px-4 py-3.5 sm:px-6">
          <div>
            <h2 className="text-base font-semibold">Discharge · {patientName}</h2>
            {!isDone ? (
              <p className="text-xs text-muted-foreground">
                Settle the balance to complete discharge
              </p>
            ) : null}
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-muted-foreground hover:bg-muted"
          >
            ✕
          </button>
        </div>

        {isDone ? (
          <div className="space-y-4 p-6">
            <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800">
              Discharged on{" "}
              {formatDate(done!.dischargePatient.admission.dischargeDate)} — dues
              settled.
            </div>
            <Button className="w-full" onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          <>
            {/* Scrollable body */}
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
              {/* Discharge date */}
              <div className="flex flex-wrap items-center gap-3">
                <Label htmlFor="dc-date" className="min-w-[110px]">
                  Discharge date
                </Label>
                <Input
                  id="dc-date"
                  type="date"
                  max={todayStr()}
                  value={dischargeDate}
                  onChange={(e) => {
                    setDischargeDate(e.target.value);
                    setPrefilled(false);
                  }}
                  className="w-full sm:w-auto sm:flex-1"
                />
              </div>

              {previewError ? (
                <p className="text-sm text-red-600">{previewError.message}</p>
              ) : !pv ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  {previewing ? "Calculating dues…" : ""}
                </p>
              ) : (
                <>
                  {/* Pro-ration card */}
                  {pv.hasCurrentCycle && Number(pv.cancelledFee) > 0 ? (
                    <div className="rounded-lg border bg-muted/30 p-3">
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>
                          Cycle{" "}
                          {pv.cycleStart ? formatDate(pv.cycleStart) : ""} →{" "}
                          {pv.cycleEnd ? formatDate(pv.cycleEnd) : ""}
                        </span>
                        <span>
                          {pv.daysStayed} of {pv.daysInPeriod} days stayed
                        </span>
                      </div>
                      <div className="mt-2 flex h-3.5 overflow-hidden rounded border">
                        <div
                          className="bg-emerald-500"
                          style={{ width: `${stayPct}%` }}
                        />
                        <div
                          className="bg-muted-foreground/25"
                          style={{ width: `${100 - stayPct}%` }}
                        />
                      </div>
                      <div className="mt-2 flex items-center justify-between text-sm">
                        <span>
                          Fee{" "}
                          <span className="text-muted-foreground line-through">
                            {rupee(pv.fullFee)}
                          </span>{" "}
                          → <b className="font-medium">{rupee(pv.proratedFee)}</b>
                        </span>
                        <span className="text-xs text-green-700">
                          {rupee(pv.cancelledFee)} cancelled
                        </span>
                      </div>
                    </div>
                  ) : null}

                  {/* Itemised dues */}
                  <div>
                    <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                      Pending dues
                    </p>
                    {pv.lines.length === 0 ? (
                      <p className="rounded-lg border bg-muted/20 p-3 text-sm text-muted-foreground">
                        Nothing outstanding — ready to discharge.
                      </p>
                    ) : (
                      <div className="overflow-hidden rounded-lg border text-sm">
                        {pv.lines.map((ln, i) => (
                          <div
                            key={`${ln.label}-${i}`}
                            className="flex justify-between gap-3 border-b px-3 py-2 last:border-b-0"
                          >
                            <span
                              className={
                                ln.kind === "charge"
                                  ? "text-muted-foreground"
                                  : ""
                              }
                            >
                              {ln.label}
                            </span>
                            <span className="whitespace-nowrap tabular-nums">
                              {rupee(ln.amount)}
                            </span>
                          </div>
                        ))}
                        <div className="flex justify-between gap-3 bg-muted/40 px-3 py-2.5 font-semibold">
                          <span>Balance to settle</span>
                          <span className="tabular-nums">
                            {rupee(pv.totalDueNow)}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Record payment */}
                  {totalDue > 0 ? (
                    <div className="space-y-3 rounded-lg border p-3">
                      <p className="text-sm font-medium">Record payment</p>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1.5">
                          <Label htmlFor="dc-fees">Fees</Label>
                          <Input
                            id="dc-fees"
                            type="number"
                            inputMode="decimal"
                            min={0}
                            step="0.01"
                            value={feesPaid}
                            onChange={(e) => setFeesPaid(e.target.value)}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="dc-charges">Charges</Label>
                          <Input
                            id="dc-charges"
                            type="number"
                            inputMode="decimal"
                            min={0}
                            step="0.01"
                            value={chargesPaid}
                            onChange={(e) => setChargesPaid(e.target.value)}
                          />
                        </div>
                      </div>
                      {acctData?.paymentAccounts?.length ? (
                        <div className="space-y-1.5">
                          <Label htmlFor="dc-acct">Account (optional)</Label>
                          <select
                            id="dc-acct"
                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            value={accountId}
                            onChange={(e) => setAccountId(e.target.value)}
                          >
                            <option value="">—</option>
                            {acctData.paymentAccounts.map((a) => (
                              <option key={a.id} value={a.id}>
                                {a.name}
                              </option>
                            ))}
                          </select>
                        </div>
                      ) : null}
                      <div className="h-2 overflow-hidden rounded-full border bg-muted">
                        <div
                          className={
                            tallied ? "h-full bg-emerald-500" : "h-full bg-amber-500"
                          }
                          style={{ width: `${payPct}%` }}
                        />
                      </div>
                      <p
                        className={`text-xs ${
                          tallied ? "text-green-700" : "text-red-600"
                        }`}
                      >
                        {tallied
                          ? `Account tallied — ${rupee(paying)} settles the balance.`
                          : `${rupee(shortfall)} still owed — collect the balance to unlock discharge.`}
                      </p>
                    </div>
                  ) : null}

                  {isFinance ? (
                    <div className="space-y-1.5">
                      <Label htmlFor="dc-refund">Refund (optional)</Label>
                      <Input
                        id="dc-refund"
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step="0.01"
                        placeholder="0.00"
                        value={refundAmount}
                        onChange={(e) => setRefundAmount(e.target.value)}
                      />
                    </div>
                  ) : null}
                </>
              )}

              {error ? (
                <p className="text-sm text-red-600">{error.message}</p>
              ) : null}
            </div>

            {/* Sticky footer */}
            <div className="flex gap-2 border-t p-4 sm:px-6">
              <Button
                type="button"
                variant="outline"
                className="flex-1"
                onClick={onClose}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="destructive"
                className="flex-1 gap-1.5"
                disabled={loading || !pv || !tallied}
                onClick={confirm}
              >
                {!loading && !tallied ? (
                  <Lock className="h-4 w-4" aria-hidden />
                ) : null}
                {loading ? "Discharging…" : "Confirm discharge"}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
