"use client";

import { useApolloClient, useMutation, useQuery } from "@apollo/client";
import { useRef, useState } from "react";

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
  PATIENT,
  PATIENT_AADHAR,
  UPDATE_PATIENT,
} from "@/lib/graphql/operations";

// Backend origin (media + upload endpoints live there, not on the Next host).
const API_ORIGIN = (
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/"
).replace(/\/graphql\/?$/, "");

function mediaUrl(path?: string | null) {
  if (!path) return null;
  return /^https?:\/\//.test(path) ? path : `${API_ORIGIN}${path}`;
}

async function uploadFile(patientId: string, kind: "photo" | "aadhar-scan", file: File) {
  const token = getAccessToken();
  const body = new FormData();
  body.append("file", file);
  const resp = await fetch(`${API_ORIGIN}/patients/${patientId}/${kind}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error ?? `Upload failed (${resp.status})`);
  }
}

export function PatientDocumentsPanel({
  patientId,
  photoUrl,
  isAdmin,
}: {
  patientId: string;
  photoUrl: string | null;
  isAdmin: boolean;
}) {
  const client = useApolloClient();
  const photoInput = useRef<HTMLInputElement>(null);
  const scanInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Aadhar is ADMIN-only — fetched separately so non-admins never request it.
  const { data: aadharData } = useQuery(PATIENT_AADHAR, {
    variables: { pk: patientId },
    skip: !isAdmin,
  });
  const aadhar = aadharData?.patient;

  const [aadharNumber, setAadharNumber] = useState<string | null>(null);
  const currentAadhar = aadharNumber ?? aadhar?.aadharNumber ?? "";

  const [updatePatient, { loading: savingAadhar }] = useMutation(UPDATE_PATIENT, {
    refetchQueries: [
      { query: PATIENT, variables: { pk: patientId } },
      { query: PATIENT_AADHAR, variables: { pk: patientId } },
    ],
  });

  async function onUpload(kind: "photo" | "aadhar-scan", file?: File) {
    if (!file) return;
    setError(null);
    setBusy(kind);
    try {
      await uploadFile(patientId, kind, file);
      await client.refetchQueries({ include: [PATIENT, PATIENT_AADHAR] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(null);
    }
  }

  const photo = mediaUrl(photoUrl);
  const scan = mediaUrl(aadhar?.aadharScanUrl);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Documents</CardTitle>
        <CardDescription>Photo and identity documents</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Photo */}
        <div className="flex items-center gap-4">
          {photo ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={photo}
              alt="Patient"
              className="h-20 w-20 rounded-lg border object-cover"
            />
          ) : (
            <div className="flex h-20 w-20 items-center justify-center rounded-lg border bg-muted text-xs text-muted-foreground">
              No photo
            </div>
          )}
          {isAdmin ? (
            <div>
              <input
                ref={photoInput}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={(e) => onUpload("photo", e.target.files?.[0])}
              />
              <Button
                variant="outline"
                size="sm"
                disabled={busy === "photo"}
                onClick={() => photoInput.current?.click()}
              >
                {busy === "photo" ? "Uploading…" : photo ? "Replace photo" : "Add photo"}
              </Button>
            </div>
          ) : null}
        </div>

        {/* Aadhar — ADMIN only */}
        {isAdmin ? (
          <div className="space-y-3 border-t pt-4">
            <div className="space-y-2">
              <Label htmlFor="aadhar">Aadhar number</Label>
              <div className="flex gap-2">
                <Input
                  id="aadhar"
                  inputMode="numeric"
                  placeholder="12 digits"
                  value={currentAadhar}
                  onChange={(e) => setAadharNumber(e.target.value)}
                />
                <Button
                  variant="outline"
                  disabled={
                    savingAadhar ||
                    (!!currentAadhar && !/^\d{12}$/.test(currentAadhar))
                  }
                  onClick={() =>
                    updatePatient({
                      variables: {
                        patientId,
                        input: { aadharNumber: currentAadhar },
                      },
                    })
                  }
                >
                  {savingAadhar ? "Saving…" : "Save"}
                </Button>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <input
                ref={scanInput}
                type="file"
                accept="image/*,application/pdf"
                className="hidden"
                onChange={(e) => onUpload("aadhar-scan", e.target.files?.[0])}
              />
              <Button
                variant="outline"
                size="sm"
                disabled={busy === "aadhar-scan"}
                onClick={() => scanInput.current?.click()}
              >
                {busy === "aadhar-scan"
                  ? "Uploading…"
                  : scan
                    ? "Replace scan"
                    : "Upload Aadhar scan"}
              </Button>
              {scan ? (
                <a
                  href={scan}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-primary hover:underline"
                >
                  View scan
                </a>
              ) : null}
            </div>
          </div>
        ) : null}

        {error ? <p className="text-sm text-red-600">{error}</p> : null}
      </CardContent>
    </Card>
  );
}
