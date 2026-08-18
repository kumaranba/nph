"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
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
import { CREATE_ADMISSION, VACANT_BEDS } from "@/lib/graphql/operations";

type VacantBedsResult = {
  beds: Array<{
    id: string;
    label: string;
    room: { id: string; name: string };
  }>;
};

type CreateAdmissionResult = {
  createAdmission: {
    id: string;
    status: string;
    patient: { id: string; patientId: string; name: string };
    bed: { id: string; label: string; status: string };
  };
};

// Mirrors CreateAdmissionInput on the server. All fields are strings in the
// form; numeric/decimal coercion happens at submit time.
type AdmissionForm = {
  name: string;
  dateOfBirth: string;
  gender: string;
  foodPreference: string;
  diagnosis: string;
  admittingDoctor: string;
  bedId: string;
  admissionDate: string;
  monthlyFee: string;
  guardianName: string;
  guardianPhone: string;
};

export default function NewAdmissionPage() {
  const router = useRouter();

  // Gate the page behind a token, consistent with the dashboard.
  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AdmissionForm>({
    defaultValues: {
      name: "",
      dateOfBirth: "",
      gender: "",
      foodPreference: "",
      diagnosis: "",
      admittingDoctor: "",
      bedId: "",
      admissionDate: new Date().toISOString().slice(0, 10),
      monthlyFee: "",
      guardianName: "",
      guardianPhone: "",
    },
  });

  // Bed picker fetches only VACANT beds.
  const { data: bedsData, loading: bedsLoading, error: bedsError } =
    useQuery<VacantBedsResult>(VACANT_BEDS);

  const [createAdmission, { loading: submitting, error: mutationError }] =
    useMutation<CreateAdmissionResult>(CREATE_ADMISSION, {
      // The new admission occupies a bed and creates a patient, so any cached
      // bed/patient lists are now stale.
      refetchQueries: [{ query: VACANT_BEDS }],
      onCompleted: (data) => {
        router.push(`/patients/${data.createAdmission.patient.id}`);
      },
      onError: () => {}, // surfaced via `mutationError` below
    });

  function onSubmit(values: AdmissionForm) {
    createAdmission({
      variables: {
        input: {
          name: values.name,
          dateOfBirth: values.dateOfBirth || null,
          gender: values.gender || undefined,
          foodPreference: values.foodPreference || undefined,
          diagnosis: values.diagnosis,
          admittingDoctor: values.admittingDoctor,
          bedId: values.bedId,
          admissionDate: values.admissionDate,
          monthlyFee: values.monthlyFee,
          guardianName: values.guardianName,
          guardianPhone: values.guardianPhone,
        },
      },
    });
  }

  if (!hasToken) return null;

  return (
    <main className="flex min-h-screen items-center justify-center p-4 sm:p-6 lg:p-8">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>New Admission</CardTitle>
          <CardDescription>
            Register a patient and admit them to a vacant bed
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            {/* Patient name */}
            <div className="space-y-2">
              <Label htmlFor="name">Patient name</Label>
              <Input
                id="name"
                {...register("name", { required: "Patient name is required" })}
              />
              {errors.name ? (
                <p className="text-sm text-red-600">{errors.name.message}</p>
              ) : null}
            </div>

            {/* DOB + gender + admission date */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="dateOfBirth">Date of birth (optional)</Label>
                <Input
                  id="dateOfBirth"
                  type="date"
                  {...register("dateOfBirth")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="gender">Gender</Label>
                <select
                  id="gender"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  defaultValue=""
                  {...register("gender")}
                >
                  <option value="">Unspecified</option>
                  <option value="MALE">Male</option>
                  <option value="FEMALE">Female</option>
                  <option value="OTHER">Other</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="admissionDate">Admission date</Label>
                <Input
                  id="admissionDate"
                  type="date"
                  {...register("admissionDate", {
                    required: "Admission date is required",
                  })}
                />
                {errors.admissionDate ? (
                  <p className="text-sm text-red-600">
                    {errors.admissionDate.message}
                  </p>
                ) : null}
              </div>
            </div>

            {/* Diagnosis */}
            <div className="space-y-2">
              <Label htmlFor="diagnosis">Diagnosis</Label>
              <Input
                id="diagnosis"
                {...register("diagnosis", { required: "Diagnosis is required" })}
              />
              {errors.diagnosis ? (
                <p className="text-sm text-red-600">{errors.diagnosis.message}</p>
              ) : null}
            </div>

            {/* Admitting doctor */}
            <div className="space-y-2">
              <Label htmlFor="admittingDoctor">Admitting doctor</Label>
              <Input
                id="admittingDoctor"
                {...register("admittingDoctor", {
                  required: "Admitting doctor is required",
                })}
              />
              {errors.admittingDoctor ? (
                <p className="text-sm text-red-600">
                  {errors.admittingDoctor.message}
                </p>
              ) : null}
            </div>

            {/* Bed picker (VACANT only) + monthly fee */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="bedId">Bed</Label>
                <select
                  id="bedId"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  defaultValue=""
                  disabled={bedsLoading}
                  {...register("bedId", { required: "Please choose a bed" })}
                >
                  <option value="" disabled>
                    {bedsLoading ? "Loading beds…" : "Select a vacant bed"}
                  </option>
                  {bedsData?.beds.map((bed) => (
                    <option key={bed.id} value={bed.id}>
                      {bed.room.name} — {bed.label}
                    </option>
                  ))}
                </select>
                {errors.bedId ? (
                  <p className="text-sm text-red-600">{errors.bedId.message}</p>
                ) : null}
                {bedsError ? (
                  <p className="text-sm text-red-600">
                    Couldn’t load beds: {bedsError.message}
                  </p>
                ) : !bedsLoading && bedsData?.beds.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No vacant beds available.
                  </p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="monthlyFee">Monthly fee</Label>
                <Input
                  id="monthlyFee"
                  type="number"
                  min={0}
                  step="0.01"
                  {...register("monthlyFee", {
                    required: "Monthly fee is required",
                    min: { value: 0, message: "Fee cannot be negative" },
                  })}
                />
                {errors.monthlyFee ? (
                  <p className="text-sm text-red-600">
                    {errors.monthlyFee.message}
                  </p>
                ) : null}
              </div>
            </div>

            {/* Guardian (optional) */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="guardianName">Guardian name (optional)</Label>
                <Input id="guardianName" {...register("guardianName")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="guardianPhone">Guardian phone (optional)</Label>
                <Input id="guardianPhone" {...register("guardianPhone")} />
              </div>
            </div>

            {mutationError ? (
              <p className="text-sm text-red-600">{mutationError.message}</p>
            ) : null}

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Admitting…" : "Admit patient"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
