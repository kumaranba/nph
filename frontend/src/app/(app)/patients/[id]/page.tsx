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
import { PatientDocumentsPanel } from "@/components/patient-documents-panel";
import { ActivityTimeline } from "@/components/activity-timeline";
import { ConsentControl } from "@/components/consent-control";
import { ContactActions } from "@/components/contact-actions";
import { PatientFollowUpsPanel } from "@/components/patient-follow-ups-panel";
import { ReadmitModal } from "@/components/readmit-modal";
import { formatDate } from "@/lib/format-date";
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
  dischargeDate: string | null;
  dischargeType: string;
  effectiveFee: { amount: string } | null;
  outstandingDue: string;
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
    alternateId: string | null;
    name: string;
    age: number | null;
    dateOfBirth: string | null;
    gender: string;
    diagnosis: string;
    foodPreference: string;
    isAlive: boolean;
    dateOfExpiry: string | null;
    photoUrl: string | null;
    guardianName: string;
    guardianPhone: string;
    admittingDoctor: string;
    place: string;
    contactConsent: string;
    doNotContact: boolean;
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
  const [showReadmit, setShowReadmit] = useState(false);
  const [actKey, setActKey] = useState(0);

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
  // PRM roles (PRO + ADMIN) see the follow-ups panel; PRO may also manage it.
  const canViewFollowUps = role === "PRO" || role === "ADMIN";
  const canManageFollowUps = role === "PRO";
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
                <Row label="Alternate ID" value={patient.alternateId || "—"} />
                <Row
                  label="Age"
                  value={patient.age === null ? "—" : String(patient.age)}
                />
                <Row
                  label="Date of birth"
                  value={patient.dateOfBirth ? formatDate(patient.dateOfBirth) : "—"}
                />
                <Row
                  label="Food preference"
                  value={
                    patient.foodPreference === "VEG"
                      ? "Vegetarian"
                      : patient.foodPreference === "NON_VEG"
                        ? "Non-vegetarian"
                        : "—"
                  }
                />
                <Row
                  label="Life status"
                  value={
                    patient.isAlive
                      ? "Alive"
                      : `Deceased${
                          patient.dateOfExpiry
                            ? ` · ${formatDate(patient.dateOfExpiry)}`
                            : ""
                        }`
                  }
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

              <AdmissionHistory admissions={patient.admissions} />

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

              {canRecordPayment ? (
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() =>
                    router.push(`/patients/${patient.id}/statement`)
                  }
                >
                  Account statement
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

          {/* Admit this existing patient: "New Admission" if they have no
              admission history, "Re Admission" after a discharge, nothing while
              an admission is active. ADMIN only. */}
          {patient && canEditPatient && !activeAdmission ? (
            <Button
              variant="outline"
              className="w-full"
              onClick={() => setShowReadmit(true)}
            >
              {patient.admissions.length > 0 ? "Re Admission" : "New Admission"}
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {patient ? (
        <PatientDocumentsPanel
          patientId={patient.id}
          photoUrl={patient.photoUrl}
          isAdmin={canEditPatient}
        />
      ) : null}

      {patient && canViewFollowUps ? (
        <PatientFollowUpsPanel
          patientId={patient.id}
          canManage={canManageFollowUps}
        />
      ) : null}

      {patient && canViewFollowUps ? (
        <Card>
          <CardHeader>
            <CardTitle>Activity</CardTitle>
            <CardDescription>Interaction history for this patient</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ConsentControl
              patientId={patient.id}
              consent={patient.contactConsent}
              doNotContact={patient.doNotContact}
              canEdit={canManageFollowUps}
              onChanged={() => refetch()}
            />
            {canManageFollowUps && patient.guardianPhone ? (
              <ContactActions
                phone={patient.guardianPhone}
                patientId={patient.id}
                consent={patient.contactConsent}
                doNotContact={patient.doNotContact}
                onLogged={() => setActKey((k) => k + 1)}
              />
            ) : null}
            <ActivityTimeline
              patientId={patient.id}
              canAdd={canManageFollowUps}
              refreshKey={actKey}
            />
          </CardContent>
        </Card>
      ) : null}

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
          onClose={() => setShowDischarge(false)}
        />
      ) : null}

      {showEdit && patient ? (
        <EditPatientModal
          patient={{
            id: patient.id,
            name: patient.name,
            alternateId: patient.alternateId,
            dateOfBirth: patient.dateOfBirth,
            gender: patient.gender,
            diagnosis: patient.diagnosis,
            admittingDoctor: patient.admittingDoctor,
            guardianName: patient.guardianName,
            guardianPhone: patient.guardianPhone,
            place: patient.place,
            foodPreference: patient.foodPreference,
            isAlive: patient.isAlive,
            dateOfExpiry: patient.dateOfExpiry,
          }}
          onClose={() => setShowEdit(false)}
        />
      ) : null}

      {showReadmit && patient ? (
        <ReadmitModal
          patientId={patient.id}
          patientName={patient.name}
          title={patient.admissions.length > 0 ? "Re Admission" : "New Admission"}
          onClose={() => setShowReadmit(false)}
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

const rupee = (n: string | number) =>
  `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

// Inclusive day count between two ISO dates (admission day through the end day).
function stayDays(fromISO: string, toISO: string): number {
  const ms =
    new Date(toISO + "T00:00:00").getTime() -
    new Date(fromISO + "T00:00:00").getTime();
  return Math.max(1, Math.floor(ms / 86_400_000) + 1);
}

// Collapsible admission-history grid: one row per stay, current first then past
// by discharge date. Columns: DOA, DOD, fee, duration, pending dues.
function AdmissionHistory({ admissions }: { admissions: Admission[] }) {
  const [open, setOpen] = useState(true);
  if (admissions.length === 0) return null;

  const todayISO = new Date().toISOString().slice(0, 10);
  const ordered = [...admissions].sort((a, b) => {
    const aActive = a.status === "ACTIVE";
    const bActive = b.status === "ACTIVE";
    if (aActive !== bActive) return aActive ? -1 : 1;
    return (b.dischargeDate ?? b.admissionDate).localeCompare(
      a.dischargeDate ?? a.admissionDate
    );
  });

  return (
    <div className="rounded-lg border">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-3 py-2.5 text-sm font-medium"
      >
        <span className="flex items-center gap-2">
          Admission
          <span className="rounded-full bg-muted px-1.5 py-0.5 text-xs font-normal text-muted-foreground">
            {admissions.length}
          </span>
        </span>
        <span className="text-muted-foreground">{open ? "▾" : "▸"}</span>
      </button>

      {open ? (
        <div className="overflow-x-auto border-t">
          <table className="w-full min-w-[440px] text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-3 py-2 font-medium">DOA</th>
                <th className="px-3 py-2 font-medium">DOD</th>
                <th className="px-3 py-2 text-right font-medium">Fees</th>
                <th className="px-3 py-2 text-right font-medium">Duration</th>
                <th className="px-3 py-2 text-right font-medium">Pending dues</th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((a) => {
                const active = a.status === "ACTIVE";
                const endISO = a.dischargeDate ?? todayISO;
                const due = Number(a.outstandingDue || 0);
                return (
                  <tr
                    key={a.id}
                    className={`border-t ${active ? "bg-green-50/60" : ""}`}
                  >
                    <td className="whitespace-nowrap px-3 py-2.5">
                      {formatDate(a.admissionDate)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      {active ? (
                        <span className="rounded-full bg-green-100 px-2 py-0.5 text-[11px] font-medium text-green-700">
                          In-patient
                        </span>
                      ) : a.dischargeDate ? (
                        formatDate(a.dischargeDate)
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-medium">
                      {a.effectiveFee ? rupee(a.effectiveFee.amount) : "—"}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right text-muted-foreground">
                      {stayDays(a.admissionDate, endISO)} days
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right">
                      {due > 0 ? (
                        <span className="font-medium text-amber-600">
                          {rupee(due)}
                        </span>
                      ) : active ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <span className="text-muted-foreground">Cleared</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
