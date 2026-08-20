"use client";

import { useMutation, useQuery } from "@apollo/client";
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
  `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;

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
  // Once the preview loads we pre-fill the payment fields — but only once, so
  // the operator's edits aren't overwritten on refetch.
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
  const paying = (Number(feesPaid) || 0) + (Number(chargesPaid) || 0);
  const shortfall = pv ? Number(pv.totalDueNow) - paying : 0;

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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Discharge patient"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-md flex-col rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Discharge patient</h2>
        <p className="mt-1 text-sm text-muted-foreground">{patientName}</p>

        {isDone ? (
          <div className="mt-4 space-y-4">
            <p className="text-sm text-green-700">
              Patient discharged on {formatDate(done!.dischargePatient.admission.dischargeDate)} — dues settled.
            </p>
            <Button className="w-full" onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
            {/* Discharge date drives the pro-ration */}
            <div className="space-y-1.5">
              <Label htmlFor="dc-date">Discharge date</Label>
              <Input
                id="dc-date"
                type="date"
                max={todayStr()}
                value={dischargeDate}
                onChange={(e) => {
                  setDischargeDate(e.target.value);
                  setPrefilled(false); // re-prefill for the new date's dues
                }}
              />
            </div>

            {previewError ? (
              <p className="text-sm text-red-600">{previewError.message}</p>
            ) : !pv ? (
              <p className="text-sm text-muted-foreground">
                {previewing ? "Calculating dues…" : ""}
              </p>
            ) : (
              <>
                {/* Pro-ration summary */}
                {pv.hasCurrentCycle && Number(pv.cancelledFee) > 0 ? (
                  <div className="rounded-md border bg-muted/40 p-3 text-sm">
                    <p className="font-medium">Current cycle — pro-rated</p>
                    <p className="mt-1 text-muted-foreground">
                      Stayed {pv.daysStayed} of {pv.daysInPeriod} days.
                      Fee {rupee(pv.fullFee)} →{" "}
                      <b className="text-foreground">{rupee(pv.proratedFee)}</b>{" "}
                      · {rupee(pv.cancelledFee)} cancelled for the unused period.
                    </p>
                  </div>
                ) : null}

                {/* Itemised dues */}
                <div>
                  <p className="mb-1 text-sm font-medium">Pending dues</p>
                  {pv.lines.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Nothing outstanding — ready to discharge.
                    </p>
                  ) : (
                    <ul className="divide-y rounded-md border text-sm">
                      {pv.lines.map((ln, i) => (
                        <li
                          key={`${ln.label}-${i}`}
                          className="flex justify-between gap-3 px-3 py-1.5"
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
                          <span className="tabular-nums">{rupee(ln.amount)}</span>
                        </li>
                      ))}
                      <li className="flex justify-between gap-3 bg-muted/40 px-3 py-2 font-semibold">
                        <span>Total due now</span>
                        <span className="tabular-nums">
                          {rupee(pv.totalDueNow)}
                        </span>
                      </li>
                    </ul>
                  )}
                </div>

                {/* Record payment */}
                {Number(pv.totalDueNow) > 0 ? (
                  <div className="space-y-3 rounded-md border p-3">
                    <p className="text-sm font-medium">Record payment</p>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="space-y-1.5">
                        <Label htmlFor="dc-fees">Fees</Label>
                        <Input
                          id="dc-fees"
                          type="number"
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
                    <p
                      className={`text-xs ${
                        shortfall > 0.005 ? "text-red-600" : "text-green-700"
                      }`}
                    >
                      Paying {rupee(paying)} of {rupee(pv.totalDueNow)}
                      {shortfall > 0.005
                        ? ` — ${rupee(shortfall)} short. Discharge is blocked until the balance is cleared.`
                        : " — balance clears."}
                    </p>
                  </div>
                ) : null}

                {isFinance ? (
                  <div className="space-y-1.5">
                    <Label htmlFor="dc-refund">Refund (optional)</Label>
                    <Input
                      id="dc-refund"
                      type="number"
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

            {error ? <p className="text-sm text-red-600">{error.message}</p> : null}

            <div className="flex gap-2 pt-1">
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
                className="flex-1"
                disabled={loading || !pv || shortfall > 0.005}
                onClick={confirm}
              >
                {loading ? "Discharging…" : "Confirm discharge"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
