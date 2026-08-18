"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PATIENT, READMIT_PATIENT, VACANT_BEDS } from "@/lib/graphql/operations";

type VacantBeds = {
  beds: Array<{ id: string; label: string; room: { id: string; name: string } }>;
};

type ReadmitForm = {
  admissionDate: string;
  monthlyFee: string;
  bedId: string;
};

export function ReadmitModal({
  patientId,
  patientName,
  title,
  onClose,
}: {
  patientId: string;
  patientName: string;
  title: string;
  onClose: () => void;
}) {
  const { register, handleSubmit } = useForm<ReadmitForm>({
    defaultValues: {
      admissionDate: new Date().toISOString().slice(0, 10),
      monthlyFee: "",
      bedId: "",
    },
  });

  const { data: bedsData, loading: bedsLoading } = useQuery<VacantBeds>(VACANT_BEDS);

  const [readmit, { loading, error }] = useMutation(READMIT_PATIENT, {
    refetchQueries: [
      { query: PATIENT, variables: { pk: patientId } },
      { query: VACANT_BEDS },
    ],
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

  function onSubmit(values: ReadmitForm) {
    readmit({
      variables: {
        patientId,
        admissionDate: values.admissionDate,
        monthlyFee: values.monthlyFee,
        bedId: values.bedId || null,
      },
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{patientName}</p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="ra-date">Admission date</Label>
            <Input
              id="ra-date"
              type="date"
              {...register("admissionDate", { required: true })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ra-fee">Monthly fee</Label>
            <Input
              id="ra-fee"
              type="number"
              min={0}
              step="0.01"
              placeholder="0.00"
              {...register("monthlyFee", { required: true })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ra-bed">Bed (optional)</Label>
            <select
              id="ra-bed"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              defaultValue=""
              disabled={bedsLoading}
              {...register("bedId")}
            >
              <option value="">No bed</option>
              {bedsData?.beds.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.room.name} — {b.label}
                </option>
              ))}
            </select>
          </div>

          {error ? <p className="text-sm text-red-600">{error.message}</p> : null}

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
              {loading ? "Admitting…" : "Admit"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
