"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
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
  ADD_BED,
  CREATE_ADMISSION,
  ROOMS_WITH_BEDS,
} from "@/lib/graphql/operations";

type BedLite = { id: string; label: string; status: string };
type RoomsResult = {
  rooms: Array<{ id: string; name: string; beds: BedLite[] }>;
};

// Preview the next auto-incremented label for a room's beds (mirrors the
// server: highest numeric suffix + 1, keeping the prefix; B1 when empty).
function nextBedLabel(beds: BedLite[]): string {
  let prefix = "B";
  let highest = 0;
  let found = false;
  for (const b of beds) {
    const m = /^\s*([A-Za-z]*)\s*(\d+)\s*$/.exec(b.label ?? "");
    if (m && (!found || Number(m[2]) > highest)) {
      found = true;
      highest = Number(m[2]);
      prefix = m[1] || "B";
    }
  }
  return `${prefix}${highest + 1}`;
}

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
    setValue,
    watch,
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

  // Bed picker: choose a room, then a vacant bed in it (or add one).
  const [roomId, setRoomId] = useState("");
  const { data: roomsData, loading: roomsLoading, error: roomsError, refetch } =
    useQuery<RoomsResult>(ROOMS_WITH_BEDS);

  const selectedBedId = watch("bedId");
  const selectedRoom = roomsData?.rooms.find((r) => r.id === roomId);
  const vacantBeds =
    selectedRoom?.beds.filter((b) => b.status === "VACANT") ?? [];

  const [addBed, { loading: addingBed, error: addBedError }] = useMutation(
    ADD_BED,
    {
      onCompleted: async (data) => {
        await refetch();
        setValue("bedId", data.addBed.id, { shouldValidate: true });
      },
      onError: () => {},
    }
  );

  const [createAdmission, { loading: submitting, error: mutationError }] =
    useMutation<CreateAdmissionResult>(CREATE_ADMISSION, {
      // The new admission occupies a bed and creates a patient, so cached
      // room/bed/patient lists are now stale.
      refetchQueries: [{ query: ROOMS_WITH_BEDS }],
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

            {/* Room + bed picker + monthly fee */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="roomId">Room</Label>
                <select
                  id="roomId"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  value={roomId}
                  disabled={roomsLoading}
                  onChange={(e) => {
                    setRoomId(e.target.value);
                    setValue("bedId", "");
                  }}
                >
                  <option value="" disabled>
                    {roomsLoading ? "Loading rooms…" : "Select a room"}
                  </option>
                  {roomsData?.rooms.map((r) => {
                    const free = r.beds.filter(
                      (b) => b.status === "VACANT"
                    ).length;
                    return (
                      <option key={r.id} value={r.id}>
                        {r.name} ({free} vacant)
                      </option>
                    );
                  })}
                </select>
                {roomsError ? (
                  <p className="text-sm text-red-600">
                    Couldn’t load rooms: {roomsError.message}
                  </p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="bedId">Bed</Label>
                <select
                  id="bedId"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={!roomId || vacantBeds.length === 0}
                  {...register("bedId", { required: "Please choose a bed" })}
                >
                  <option value="" disabled>
                    {!roomId
                      ? "Select a room first"
                      : vacantBeds.length === 0
                        ? "No vacant beds"
                        : "Select a vacant bed"}
                  </option>
                  {vacantBeds.map((bed) => (
                    <option key={bed.id} value={bed.id}>
                      {bed.label}
                    </option>
                  ))}
                </select>
                {errors.bedId && !selectedBedId ? (
                  <p className="text-sm text-red-600">{errors.bedId.message}</p>
                ) : null}
                {roomId && vacantBeds.length === 0 && selectedRoom ? (
                  <div className="space-y-1">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="w-full"
                      disabled={addingBed}
                      onClick={() => addBed({ variables: { roomId } })}
                    >
                      {addingBed
                        ? "Adding bed…"
                        : `Add bed ${nextBedLabel(selectedRoom.beds)} to ${selectedRoom.name}`}
                    </Button>
                    {addBedError ? (
                      <p className="text-sm text-red-600">
                        {addBedError.message}
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        This room is full — add a bed to admit here.
                      </p>
                    )}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
