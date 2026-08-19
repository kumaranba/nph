"use client";

import { useMutation } from "@apollo/client";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CREATE_STAFF, UPDATE_STAFF } from "@/lib/graphql/operations";

export const DESIGNATIONS: Array<{ value: string; label: string }> = [
  { value: "NURSE", label: "Nurse" },
  { value: "ATTENDANT", label: "Attendant" },
  { value: "COOK", label: "Cook" },
  { value: "CLEANER", label: "Cleaner" },
  { value: "SECURITY", label: "Security" },
  { value: "ADMIN_STAFF", label: "Administrative" },
  { value: "OTHER", label: "Other" },
];

export type StaffRow = {
  id: string;
  staffCode: string;
  name: string;
  designation: string;
  phone: string;
  isActive: boolean;
  joinedOn: string | null;
};

type StaffForm = {
  name: string;
  designation: string;
  phone: string;
  joinedOn: string;
};

export function StaffFormModal({
  staff,
  onClose,
  onSaved,
}: {
  staff?: StaffRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!staff;
  const { register, handleSubmit } = useForm<StaffForm>({
    defaultValues: {
      name: staff?.name ?? "",
      designation: staff?.designation ?? "OTHER",
      phone: staff?.phone ?? "",
      joinedOn: staff?.joinedOn ?? "",
    },
  });

  const done = () => {
    onSaved();
    onClose();
  };

  const [create, { loading: creating, error: createErr }] = useMutation(
    CREATE_STAFF,
    { onCompleted: done, onError: () => {} }
  );
  const [update, { loading: updating, error: updateErr }] = useMutation(
    UPDATE_STAFF,
    { onCompleted: done, onError: () => {} }
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const loading = creating || updating;
  const error = createErr || updateErr;

  function onSubmit(values: StaffForm) {
    const payload = {
      name: values.name,
      designation: values.designation,
      phone: values.phone,
      joinedOn: values.joinedOn || null,
    };
    if (isEdit) {
      update({ variables: { id: staff!.id, data: payload } });
    } else {
      create({ variables: { data: payload } });
    }
  }

  function toggleActive() {
    update({
      variables: { id: staff!.id, data: { isActive: !staff!.isActive } },
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={isEdit ? "Edit staff" : "Add staff"}
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">
          {isEdit ? "Edit staff" : "Add staff"}
        </h2>
        {isEdit ? (
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            {staff!.staffCode}
          </p>
        ) : null}

        <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="st-name">Name</Label>
            <Input
              id="st-name"
              placeholder="Full name"
              {...register("name", { required: true })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="st-desig">Designation</Label>
            <select
              id="st-desig"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              {...register("designation")}
            >
              {DESIGNATIONS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="st-phone">Phone (optional)</Label>
            <Input id="st-phone" placeholder="Mobile number" {...register("phone")} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="st-joined">Joined on (optional)</Label>
            <Input id="st-joined" type="date" {...register("joinedOn")} />
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
              {loading ? "Saving…" : isEdit ? "Save" : "Add staff"}
            </Button>
          </div>
        </form>

        {isEdit ? (
          <div className="mt-4 border-t pt-4">
            <Button
              type="button"
              variant={staff!.isActive ? "destructive" : "outline"}
              className="w-full"
              disabled={loading}
              onClick={toggleActive}
            >
              {staff!.isActive ? "Deactivate" : "Reactivate"}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
