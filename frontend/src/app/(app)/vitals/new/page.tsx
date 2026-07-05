"use client";

import { useQuery, useMutation } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
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
  CREATE_VITAL_READING,
  ME,
  PATIENT,
  SEARCH_PATIENTS,
} from "@/lib/graphql/operations";
import { useDebounce } from "@/lib/use-debounce";

type SearchRow = { id: string; patientId: string; name: string };
type SearchResult = { searchPatients: SearchRow[] };
type MeResult = { me: { role: string } };
type PatientResult = {
  patient: {
    id: string;
    name: string;
    admissions: { id: string; status: string }[];
  } | null;
};

type VitalsForm = {
  bpSystolic: string;
  bpDiastolic: string;
  pulse: string;
  temperature: string;
  spo2: string;
  weight: string;
  notes: string;
};

// Maps a flagged vital code to a label and the form field it came from.
const VITAL_META: Record<string, { label: string; field: keyof VitalsForm }> = {
  BP_SYSTOLIC: { label: "BP systolic", field: "bpSystolic" },
  BP_DIASTOLIC: { label: "BP diastolic", field: "bpDiastolic" },
  PULSE: { label: "Pulse", field: "pulse" },
  TEMPERATURE: { label: "Temperature", field: "temperature" },
  SPO2: { label: "SpO₂", field: "spo2" },
  WEIGHT: { label: "Weight", field: "weight" },
};

// Big touch-friendly numeric field.
function VitalField({
  id,
  label,
  unit,
  decimal,
  register,
  required = true,
}: {
  id: keyof VitalsForm;
  label: string;
  unit?: string;
  decimal?: boolean;
  register: ReturnType<typeof useForm<VitalsForm>>["register"];
  required?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-base">
        {label}
        {unit ? <span className="text-muted-foreground"> ({unit})</span> : null}
      </Label>
      <Input
        id={id}
        type="number"
        inputMode={decimal ? "decimal" : "numeric"}
        step={decimal ? "0.1" : "1"}
        min={0}
        className="h-14 text-lg"
        {...register(id, { required })}
      />
    </div>
  );
}

export default function NewVitalReadingPage() {
  const router = useRouter();

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  // Session auto-suggested from time of day; user can override.
  const [session, setSession] = useState<"AM" | "PM">(
    new Date().getHours() < 12 ? "AM" : "PM"
  );
  const [term, setTerm] = useState("");
  const [selected, setSelected] = useState<SearchRow | null>(null);
  const [submitted, setSubmitted] = useState<VitalsForm | null>(null);
  const [flagged, setFlagged] = useState<string[] | null>(null);

  const debouncedTerm = useDebounce(term, 300);

  const { data: meData, loading: meLoading } = useQuery<MeResult>(ME, {
    skip: !hasToken,
  });
  const role = meData?.me.role ?? "";
  const allowed = role === "ADMIN" || role === "NURSE";

  const { data: searchData, loading: searching } = useQuery<SearchResult>(
    SEARCH_PATIENTS,
    {
      variables: { query: debouncedTerm.trim() },
      skip: !allowed || selected !== null || debouncedTerm.trim() === "",
    }
  );

  // Resolve the selected patient's active admission.
  const { data: patientData } = useQuery<PatientResult>(PATIENT, {
    variables: { pk: selected?.id },
    skip: !selected,
  });
  const activeAdmission = patientData?.patient?.admissions.find(
    (a) => a.status === "ACTIVE"
  );

  const { register, handleSubmit, reset } = useForm<VitalsForm>({
    defaultValues: {
      bpSystolic: "",
      bpDiastolic: "",
      pulse: "",
      temperature: "",
      spo2: "",
      weight: "",
      notes: "",
    },
  });

  const [createVital, { loading: submitting, error }] = useMutation(
    CREATE_VITAL_READING,
    { onError: () => {} }
  );

  const flaggedDetails = useMemo(() => {
    if (!flagged || !submitted) return [];
    return flagged.map((code) => {
      const meta = VITAL_META[code];
      return {
        label: meta?.label ?? code,
        value: meta ? submitted[meta.field] : "",
      };
    });
  }, [flagged, submitted]);

  if (!hasToken || meLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (!allowed) {
    return (
      <main className="mx-auto min-h-screen max-w-md p-6">
        <Card>
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
            <CardDescription>
              Vitals entry is available to Nurse and Admin only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  function onSubmit(values: VitalsForm) {
    if (!activeAdmission) return;
    createVital({
      variables: {
        admissionId: activeAdmission.id,
        session,
        bpSystolic: Number(values.bpSystolic),
        bpDiastolic: Number(values.bpDiastolic),
        pulse: Number(values.pulse),
        temperature: values.temperature,
        spo2: Number(values.spo2),
        weight: values.weight === "" ? null : values.weight,
        notes: values.notes,
      },
      onCompleted: (data) => {
        setSubmitted(values);
        setFlagged(data.createVitalReading.flaggedVitals);
        reset();
      },
    });
  }

  return (
    <main className="mx-auto min-h-screen max-w-md space-y-4 p-4">
      <h1 className="text-xl font-semibold">Record vitals</h1>

      {/* Out-of-range alert after a successful save */}
      {flagged !== null ? (
        flagged.length > 0 ? (
          <div className="rounded-lg border-2 border-red-500 bg-red-50 p-4">
            <p className="text-base font-semibold text-red-700">
              ⚠ Out-of-range vitals
            </p>
            <ul className="mt-2 space-y-1 text-sm text-red-700">
              {flaggedDetails.map((f) => (
                <li key={f.label}>
                  <span className="font-medium">{f.label}:</span> {f.value}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="rounded-lg border border-green-500 bg-green-50 p-4 text-sm text-green-700">
            ✓ Vitals recorded. All values within range.
          </div>
        )
      ) : null}

      {/* Patient selection by name search */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Patient</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {selected ? (
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="font-medium">{selected.name}</p>
                <p className="font-mono text-xs text-muted-foreground">
                  {selected.patientId}
                </p>
                {!activeAdmission ? (
                  <p className="mt-1 text-sm text-red-600">
                    Not currently admitted — cannot record vitals.
                  </p>
                ) : null}
              </div>
              <Button
                variant="outline"
                onClick={() => {
                  setSelected(null);
                  setFlagged(null);
                }}
              >
                Change
              </Button>
            </div>
          ) : (
            <>
              <Input
                type="search"
                inputMode="search"
                autoFocus
                placeholder="Search patient by name…"
                className="h-14 text-lg"
                value={term}
                onChange={(e) => setTerm(e.target.value)}
              />
              {searching ? (
                <p className="text-sm text-muted-foreground">Searching…</p>
              ) : null}
              <ul className="divide-y">
                {(searchData?.searchPatients ?? []).map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className="w-full py-3 text-left active:bg-muted"
                      onClick={() => {
                        setSelected(p);
                        setTerm("");
                      }}
                    >
                      <span className="font-medium">{p.name}</span>{" "}
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

      {/* Vitals form — only once an active admission is resolved */}
      {selected && activeAdmission ? (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Session AM/PM as large toggles */}
          <div className="space-y-1.5">
            <Label className="text-base">Session</Label>
            <div className="grid grid-cols-2 gap-3">
              {(["AM", "PM"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSession(s)}
                  className={`h-14 rounded-md border text-lg font-medium ${
                    session === s
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input bg-background"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          <Card>
            <CardContent className="space-y-4 pt-6">
              <div className="grid grid-cols-2 gap-3">
                <VitalField id="bpSystolic" label="BP sys" unit="mmHg" register={register} />
                <VitalField id="bpDiastolic" label="BP dia" unit="mmHg" register={register} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <VitalField id="pulse" label="Pulse" unit="bpm" register={register} />
                <VitalField id="spo2" label="SpO₂" unit="%" register={register} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <VitalField id="temperature" label="Temp" unit="°F" decimal register={register} />
                <VitalField
                  id="weight"
                  label="Weight"
                  unit="kg"
                  decimal
                  required={false}
                  register={register}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="notes" className="text-base">
                  Notes (optional)
                </Label>
                <Input id="notes" className="h-14 text-lg" {...register("notes")} />
              </div>
            </CardContent>
          </Card>

          {error ? <p className="text-sm text-red-600">{error.message}</p> : null}

          <Button type="submit" className="h-14 w-full text-lg" disabled={submitting}>
            {submitting ? "Saving…" : "Save vitals"}
          </Button>
        </form>
      ) : null}
    </main>
  );
}
