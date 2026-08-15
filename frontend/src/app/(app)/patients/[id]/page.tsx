"use client";

import { useQuery } from "@apollo/client";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  AdditionalChargesPanel,
  type Charge,
} from "@/components/additional-charges-panel";
import { DischargeModal } from "@/components/discharge-modal";
import { EditPatientModal } from "@/components/edit-patient-modal";
import { PatientTagsPanel } from "@/components/patient-tags-panel";
import { type Tag } from "@/components/tag-input";
import { LinesSkeleton, QueryError } from "@/components/query-states";
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
  openingBalance: string;
  openingBalanceDue: string;
  hasOutstandingDues: boolean;
  outstandingInvoiceCount: number;
  bed: { id: string; label: string; room: { id: string; name: string } } | null;
  additionalCharges: Charge[];
};

type PatientResult = {
  patient: {
    id: string;
    patientId: string;
    name: string;
    age: number | null;
    gender: string;
    diagnosis: string;
    guardianName: string;
    guardianPhone: string;
    admittingDoctor: string;
    place: string;
    createdAt: string;
    tags: Tag[];
    admissions: Admission[];
  } | null;
};

type MeResult = { me: { id: string; email: string; role: string } };

export default function PatientProfilePage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const [showDischarge, setShowDischarge] = useState(false);
  const [showEdit, setShowEdit] = useState(false);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data, loading, error, refetch } = useQuery<PatientResult>(PATIENT, {
    variables: { pk: params.id },
    skip: !hasToken,
  });
  const { data: meData } = useQuery<MeResult>(ME, { skip: !hasToken });

  if (!hasToken || loading) {
    return (
      <main className="mx-auto min-h-screen w-full max-w-md p-4 sm:p-6 lg:p-8">
        <LinesSkeleton lines={6} />
      </main>
    );
  }

  if (error) {
    return (
      <main className="mx-auto min-h-screen w-full max-w-md p-4 sm:p-6 lg:p-8">
        <QueryError message={error.message} onRetry={() => refetch()} />
      </main>
    );
  }

  const patient = data?.patient;
  const role = meData?.me.role ?? "";
  const isFinance = role === "FINANCE";
  const activeAdmission = patient?.admissions.find(
    (a) => a.status === "ACTIVE"
  );
  // ADMIN and FINANCE may discharge; NURSE may not.
  const canDischarge = role === "ADMIN" || role === "FINANCE";
  // ADMIN and FINANCE may record payments.
  const canRecordPayment = role === "ADMIN" || role === "FINANCE";
  // ADMIN and NURSE (clinical staff) may edit tags; FINANCE is view-only.
  const canEditTags = role === "ADMIN" || role === "NURSE";
  // Only ADMIN may edit patient profile details.
  const canEditPatient = role === "ADMIN";
  // Show the charge log for the active admission, else the most recent one.
  const chargesAdmission =
    activeAdmission ??
    (patient
      ? [...patient.admissions].sort((a, b) =>
          b.admissionDate.localeCompare(a.admissionDate)
        )[0]
      : undefined);

  return (
    <main className="mx-auto min-h-screen w-full max-w-md space-y-6 p-4 sm:p-6 lg:p-8">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>
                {patient ? patient.name : "Patient not found"}
              </CardTitle>
              {patient ? (
                <CardDescription>{patient.patientId}</CardDescription>
              ) : null}
            </div>
            {patient && canEditPatient ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowEdit(true)}
              >
                Edit
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {patient ? (
            <>
              <dl className="space-y-2 text-sm">
                <Row
                  label="Age"
                  value={patient.age === null ? "—" : String(patient.age)}
                />
                <Row label="Diagnosis" value={patient.diagnosis} />
                <Row label="Admitting doctor" value={patient.admittingDoctor} />
                <Row label="Place" value={patient.place || "—"} />
                <Row label="Guardian" value={patient.guardianName || "—"} />
                <Row
                  label="Guardian phone"
                  value={patient.guardianPhone || "—"}
                />
                <Row
                  label="Status"
                  value={
                    activeAdmission
                      ? activeAdmission.bed
                        ? `Admitted · ${activeAdmission.bed.room.name} ${activeAdmission.bed.label}`
                        : "Admitted · no bed assigned"
                      : "Not currently admitted"
                  }
                />
                {activeAdmission && Number(activeAdmission.openingBalanceDue) > 0 ? (
                  <Row
                    label="Opening balance due"
                    value={`₹${Number(
                      activeAdmission.openingBalanceDue
                    ).toLocaleString("en-IN")}`}
                  />
                ) : null}
              </dl>

              <PatientTagsPanel
                patientId={patient.id}
                tags={patient.tags}
                canEdit={canEditTags}
              />

              <Button
                variant="outline"
                className="w-full"
                onClick={() =>
                  router.push(
                    `/patients/${patient.id}/invoices/${new Date()
                      .toISOString()
                      .slice(0, 7)}`
                  )
                }
              >
                View current invoice
              </Button>

              {canRecordPayment ? (
                <Button
                  className="w-full"
                  onClick={() =>
                    router.push(
                      `/payments/new?id=${patient.id}` +
                        `&name=${encodeURIComponent(patient.name)}` +
                        `&code=${encodeURIComponent(patient.patientId)}`
                    )
                  }
                >
                  Record payment
                </Button>
              ) : null}

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

      {patient && chargesAdmission ? (
        <AdditionalChargesPanel
          admissionId={chargesAdmission.id}
          patientId={patient.id}
          charges={chargesAdmission.additionalCharges}
          isFinance={isFinance}
          isActive={chargesAdmission.status === "ACTIVE"}
        />
      ) : null}

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

      {showEdit && patient ? (
        <EditPatientModal
          patient={{
            id: patient.id,
            name: patient.name,
            age: patient.age,
            gender: patient.gender,
            diagnosis: patient.diagnosis,
            admittingDoctor: patient.admittingDoctor,
            guardianName: patient.guardianName,
            guardianPhone: patient.guardianPhone,
            place: patient.place,
          }}
          onClose={() => setShowEdit(false)}
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
