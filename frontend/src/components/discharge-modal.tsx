"use client";

import { useMutation } from "@apollo/client";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DISCHARGE_PATIENT, PATIENT } from "@/lib/graphql/operations";

type DischargeResult = {
  dischargePatient: {
    hasOutstandingDues: boolean;
    outstandingInvoiceCount: number;
    refundAmount: string;
    admission: { id: string; status: string; dischargeDate: string };
  };
};

type DischargeForm = {
  refundAmount: string;
};

type Props = {
  admissionId: string;
  patientId: string;
  patientName: string;
  /** Current user's role; the refund field is only shown to FINANCE. */
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

  const { register, handleSubmit } = useForm<DischargeForm>({
    defaultValues: { refundAmount: "" },
  });

  const [discharge, { data, loading, error }] = useMutation<DischargeResult>(
    DISCHARGE_PATIENT,
    {
      // Refetch the patient so the profile reflects the discharged admission.
      refetchQueries: [{ query: PATIENT, variables: { pk: patientId } }],
      onError: () => {}, // surfaced via `error` below
    }
  );

  // Close on Escape for accessibility.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const result = data?.dischargePatient;
  const done = Boolean(result);

  function onSubmit(values: DischargeForm) {
    // Only Finance may send a refund; others omit the field entirely.
    const refundAmount =
      isFinance && values.refundAmount !== ""
        ? values.refundAmount
        : null;
    discharge({ variables: { admissionId, refundAmount } });
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
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Discharge patient</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {patientName}
        </p>

        {done ? (
          // --- Post-discharge summary --------------------------------------
          <div className="mt-4 space-y-4">
            {result!.hasOutstandingDues ? (
              <div className="rounded-md border border-red-300 bg-red-50 p-3">
                <p className="text-sm font-medium text-red-700">
                  Outstanding dues
                </p>
                <p className="text-sm text-red-600">
                  This patient still has {result!.outstandingInvoiceCount} unpaid
                  invoice
                  {result!.outstandingInvoiceCount === 1 ? "" : "s"}. Discharge
                  completed — please follow up on billing.
                </p>
              </div>
            ) : (
              <p className="text-sm text-green-700">
                Patient discharged. No outstanding dues.
              </p>
            )}

            <Button className="w-full" onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          // --- Discharge form ----------------------------------------------
          <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-4">
            {isFinance ? (
              <div className="space-y-2">
                <Label htmlFor="refundAmount">Refund amount (optional)</Label>
                <Input
                  id="refundAmount"
                  type="number"
                  min={0}
                  step="0.01"
                  placeholder="0.00"
                  {...register("refundAmount")}
                />
                <p className="text-xs text-muted-foreground">
                  Only Finance can record a refund.
                </p>
              </div>
            ) : null}

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
                {loading ? "Discharging…" : "Confirm discharge"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
