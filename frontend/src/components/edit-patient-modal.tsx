"use client";

import { useMutation } from "@apollo/client";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PATIENT, UPDATE_PATIENT } from "@/lib/graphql/operations";

export type EditablePatient = {
  id: string;
  name: string;
  alternateId: string | null;
  dateOfBirth: string | null;
  gender: string;
  diagnosis: string;
  admittingDoctor: string;
  guardianName: string;
  guardianPhone: string;
  place: string;
  foodPreference: string;
  isAlive: boolean;
  dateOfExpiry: string | null;
};

type EditForm = {
  name: string;
  alternateId: string;
  dateOfBirth: string;
  gender: string;
  diagnosis: string;
  admittingDoctor: string;
  guardianName: string;
  guardianPhone: string;
  place: string;
  foodPreference: string;
  isAlive: boolean;
  dateOfExpiry: string;
};

export function EditPatientModal({
  patient,
  onClose,
}: {
  patient: EditablePatient;
  onClose: () => void;
}) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<EditForm>({
    defaultValues: {
      name: patient.name,
      alternateId: patient.alternateId ?? "",
      dateOfBirth: patient.dateOfBirth ?? "",
      gender: patient.gender ?? "",
      diagnosis: patient.diagnosis,
      admittingDoctor: patient.admittingDoctor,
      guardianName: patient.guardianName,
      guardianPhone: patient.guardianPhone,
      place: patient.place,
      foodPreference: patient.foodPreference ?? "",
      isAlive: patient.isAlive,
      dateOfExpiry: patient.dateOfExpiry ?? "",
    },
  });
  const isAlive = watch("isAlive");

  const [update, { loading, error }] = useMutation(UPDATE_PATIENT, {
    refetchQueries: [{ query: PATIENT, variables: { pk: patient.id } }],
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

  function onSubmit(values: EditForm) {
    update({
      variables: {
        patientId: patient.id,
        input: {
          name: values.name,
          alternateId: values.alternateId.trim() || null,
          dateOfBirth: values.dateOfBirth || null,
          gender: values.gender || null,
          diagnosis: values.diagnosis,
          admittingDoctor: values.admittingDoctor,
          guardianName: values.guardianName,
          guardianPhone: values.guardianPhone,
          place: values.place,
          foodPreference: values.foodPreference || null,
          isAlive: values.isAlive,
          dateOfExpiry: values.isAlive ? null : values.dateOfExpiry || null,
        },
      },
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Edit patient"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Edit patient</h2>
        <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="edit-name">Name</Label>
            <Input
              id="edit-name"
              {...register("name", { required: "Name is required" })}
            />
            {errors.name ? (
              <p className="text-sm text-red-600">{errors.name.message}</p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit-altid">Alternate ID (optional)</Label>
            <Input
              id="edit-altid"
              placeholder="e.g. old register no."
              {...register("alternateId")}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit-dob">Date of birth</Label>
              <Input id="edit-dob" type="date" {...register("dateOfBirth")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-gender">Gender</Label>
              <select
                id="edit-gender"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                {...register("gender")}
              >
                <option value="">Unspecified</option>
                <option value="MALE">Male</option>
                <option value="FEMALE">Female</option>
                <option value="OTHER">Other</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit-food">Food preference</Label>
            <select
              id="edit-food"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              {...register("foodPreference")}
            >
              <option value="">Unspecified</option>
              <option value="VEG">Vegetarian</option>
              <option value="NON_VEG">Non-vegetarian</option>
            </select>
          </div>

          <div className="flex items-center gap-3">
            <input
              id="edit-alive"
              type="checkbox"
              className="h-4 w-4"
              {...register("isAlive")}
            />
            <Label htmlFor="edit-alive">Alive</Label>
            {!isAlive ? (
              <div className="ml-auto flex items-center gap-2">
                <Label htmlFor="edit-expiry" className="text-sm">
                  Date of expiry
                </Label>
                <Input
                  id="edit-expiry"
                  type="date"
                  className="w-40"
                  {...register("dateOfExpiry")}
                />
              </div>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit-diagnosis">Diagnosis</Label>
            <Input id="edit-diagnosis" {...register("diagnosis")} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit-doctor">Admitting doctor</Label>
            <Input id="edit-doctor" {...register("admittingDoctor")} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit-guardian">Guardian name</Label>
              <Input id="edit-guardian" {...register("guardianName")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-phone">Guardian phone</Label>
              <Input id="edit-phone" {...register("guardianPhone")} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit-place">Place</Label>
            <Input id="edit-place" {...register("place")} />
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
            >
              Cancel
            </Button>
            <Button type="submit" className="flex-1" disabled={loading}>
              {loading ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
