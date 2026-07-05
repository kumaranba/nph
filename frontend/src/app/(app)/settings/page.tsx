"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

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
import { LinesSkeleton, QueryError } from "@/components/query-states";
import { getAccessToken } from "@/lib/auth";
import { ME, SYSTEM_SETTINGS, UPDATE_SETTINGS } from "@/lib/graphql/operations";

type Threshold = {
  vitalType: string;
  belowThreshold: string | null;
  aboveThreshold: string | null;
};

type SettingsResult = {
  systemSettings: {
    feeDueWarningDays: number;
    vitalsThresholds: Threshold[];
  };
};

// All vital types the settings page can edit, with friendly labels.
const VITAL_TYPES = [
  { code: "BP_SYSTOLIC", label: "BP systolic" },
  { code: "BP_DIASTOLIC", label: "BP diastolic" },
  { code: "PULSE", label: "Pulse" },
  { code: "TEMPERATURE", label: "Temperature" },
  { code: "SPO2", label: "SpO₂" },
  { code: "WEIGHT", label: "Weight" },
];

// Local editable state: strings so inputs can be cleared to mean "unbounded".
type ThresholdEdit = { below: string; above: string };

export default function SettingsPage() {
  const router = useRouter();

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data: meData, loading: meLoading } = useQuery(ME, { skip: !hasToken });
  const role = (meData as { me?: { role: string } })?.me?.role ?? "";
  const isAdmin = role === "ADMIN";

  const [feeDays, setFeeDays] = useState("");
  const [edits, setEdits] = useState<Record<string, ThresholdEdit>>({});
  const [saved, setSaved] = useState(false);

  const {
    data: settingsData,
    loading,
    error: settingsError,
    refetch: refetchSettings,
  } = useQuery<SettingsResult>(SYSTEM_SETTINGS, {
    skip: !hasToken || !isAdmin,
  });

  // Seed the editable form from the fetched settings once they arrive.
  useEffect(() => {
    if (!settingsData) return;
    setFeeDays(String(settingsData.systemSettings.feeDueWarningDays));
    const byType = Object.fromEntries(
      settingsData.systemSettings.vitalsThresholds.map((t) => [t.vitalType, t])
    );
    setEdits(
      Object.fromEntries(
        VITAL_TYPES.map((v) => [
          v.code,
          {
            below: byType[v.code]?.belowThreshold ?? "",
            above: byType[v.code]?.aboveThreshold ?? "",
          },
        ])
      )
    );
  }, [settingsData]);

  const [updateSettings, { loading: saving, error }] = useMutation(
    UPDATE_SETTINGS,
    { onCompleted: () => setSaved(true), onError: () => {} }
  );

  function setEdit(code: string, side: "below" | "above", value: string) {
    setSaved(false);
    setEdits((prev) => ({ ...prev, [code]: { ...prev[code], [side]: value } }));
  }

  function onSave() {
    const thresholds = VITAL_TYPES.map((v) => ({
      vitalType: v.code,
      belowThreshold: edits[v.code]?.below === "" ? null : edits[v.code]?.below,
      aboveThreshold: edits[v.code]?.above === "" ? null : edits[v.code]?.above,
    }));
    updateSettings({
      variables: {
        feeDueWarningDays: feeDays === "" ? null : Number(feeDays),
        thresholds,
      },
    });
  }

  if (!hasToken || meLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (!isAdmin) {
    return (
      <main className="mx-auto min-h-screen max-w-2xl p-8">
        <Card>
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
            <CardDescription>
              System settings are available to Admin only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-2xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">System settings</h1>

      {loading ? (
        <LinesSkeleton lines={6} />
      ) : settingsError ? (
        <QueryError
          message={settingsError.message}
          onRetry={() => refetchSettings()}
        />
      ) : (
        <>
          {/* Billing */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Billing</CardTitle>
              <CardDescription>
                How many days ahead the fees-due list looks by default.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="max-w-xs space-y-1.5">
                <Label htmlFor="feeDays">Fee due warning days</Label>
                <Input
                  id="feeDays"
                  type="number"
                  min={0}
                  value={feeDays}
                  onChange={(e) => {
                    setSaved(false);
                    setFeeDays(e.target.value);
                  }}
                />
              </div>
            </CardContent>
          </Card>

          {/* Vitals thresholds */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Vitals thresholds</CardTitle>
              <CardDescription>
                Readings below/above these values are flagged. Leave a field
                blank for no bound on that side.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Vital</th>
                    <th className="py-2 pr-4 font-medium">Below (low)</th>
                    <th className="py-2 font-medium">Above (high)</th>
                  </tr>
                </thead>
                <tbody>
                  {VITAL_TYPES.map((v) => (
                    <tr key={v.code} className="border-b last:border-0">
                      <td className="py-2 pr-4">{v.label}</td>
                      <td className="py-2 pr-4">
                        <Input
                          type="number"
                          step="0.1"
                          className="w-28"
                          placeholder="—"
                          value={edits[v.code]?.below ?? ""}
                          onChange={(e) =>
                            setEdit(v.code, "below", e.target.value)
                          }
                        />
                      </td>
                      <td className="py-2">
                        <Input
                          type="number"
                          step="0.1"
                          className="w-28"
                          placeholder="—"
                          value={edits[v.code]?.above ?? ""}
                          onChange={(e) =>
                            setEdit(v.code, "above", e.target.value)
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {error ? (
            <p className="text-sm text-red-600">{error.message}</p>
          ) : null}
          {saved ? (
            <p className="text-sm text-green-700">Settings saved.</p>
          ) : null}

          <Button onClick={onSave} disabled={saving}>
            {saving ? "Saving…" : "Save settings"}
          </Button>
        </>
      )}
    </main>
  );
}
