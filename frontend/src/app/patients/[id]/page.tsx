"use client";

import { useQuery } from "@apollo/client";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getAccessToken } from "@/lib/auth";
import { PATIENT } from "@/lib/graphql/operations";

type PatientResult = {
  patient: {
    id: string;
    patientId: string;
    name: string;
    age: number;
    diagnosis: string;
    guardianName: string;
    guardianPhone: string;
    admittingDoctor: string;
    createdAt: string;
  } | null;
};

export default function PatientProfilePage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data, loading } = useQuery<PatientResult>(PATIENT, {
    variables: { pk: params.id },
    skip: !hasToken,
  });

  if (!hasToken || loading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  const patient = data?.patient;

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{patient ? patient.name : "Patient not found"}</CardTitle>
          {patient ? (
            <CardDescription>{patient.patientId}</CardDescription>
          ) : null}
        </CardHeader>
        <CardContent className="space-y-4">
          {patient ? (
            <dl className="space-y-2 text-sm">
              <Row label="Age" value={String(patient.age)} />
              <Row label="Diagnosis" value={patient.diagnosis} />
              <Row label="Admitting doctor" value={patient.admittingDoctor} />
              <Row label="Guardian" value={patient.guardianName || "—"} />
              <Row label="Guardian phone" value={patient.guardianPhone || "—"} />
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">
              No patient exists with this id.
            </p>
          )}

          <Button
            variant="outline"
            className="w-full"
            onClick={() => router.push("/admissions/new")}
          >
            New admission
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{value}</dd>
    </div>
  );
}
