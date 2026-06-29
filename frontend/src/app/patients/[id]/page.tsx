"use client";

import { useQuery } from "@apollo/client";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DischargeModal } from "@/components/discharge-modal";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getAccessToken } from "@/lib/auth";
import { ME, PATIENT } from "@/lib/graphql/operations";

type Admission = {
  id: string;
  status: string;
  admissionDate: string;
  hasOutstandingDues: boolean;
  outstandingInvoiceCount: number;
  bed: { id: string; label: string; room: { id: string; name: string } };
};

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
    admissions: Admission[];
  } | null;
};

type MeResult = { me: { id: string; email: string; role: string } };

export default function PatientProfilePage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const [showDischarge, setShowDischarge] = useState(false);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data, loading } = useQuery<PatientResult>(PATIENT, {
    variables: { pk: params.id },
    skip: !hasToken,
  });
  const { data: meData } = useQuery<MeResult>(ME, { skip: !hasToken });

  if (!hasToken || loading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  const patient = data?.patient;
  const role = meData?.me.role ?? "";
  const activeAdmission = patient?.admissions.find(
    (a) => a.status === "ACTIVE"
  );
  // ADMIN and FINANCE may discharge; NURSE may not.
  const canDischarge = role === "ADMIN" || role === "FINANCE";

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
            <>
              <dl className="space-y-2 text-sm">
                <Row label="Age" value={String(patient.age)} />
                <Row label="Diagnosis" value={patient.diagnosis} />
                <Row label="Admitting doctor" value={patient.admittingDoctor} />
                <Row label="Guardian" value={patient.guardianName || "—"} />
                <Row
                  label="Guardian phone"
                  value={patient.guardianPhone || "—"}
                />
                <Row
                  label="Status"
                  value={
                    activeAdmission
                      ? `Admitted · ${activeAdmission.bed.room.name} ${activeAdmission.bed.label}`
                      : "Not currently admitted"
                  }
                />
              </dl>

              {activeAdmission && canDischarge ? (
                <Button
                  variant="destructive"
                  className="w-full"
                  onClick={() => setShowDischarge(true)}
                >
                  Discharge
                </Button>
              ) : null}
            </>
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

      {showDischarge && patient && activeAdmission ? (
        <DischargeModal
          admissionId={activeAdmission.id}
          patientId={patient.id}
          patientName={patient.name}
          role={role}
          hasOutstandingDues={activeAdmission.hasOutstandingDues}
          outstandingInvoiceCount={activeAdmission.outstandingInvoiceCount}
          onClose={() => setShowDischarge(false)}
        />
      ) : null}
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
