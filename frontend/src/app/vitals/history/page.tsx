"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { VitalChart } from "@/components/vital-chart";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getAccessToken } from "@/lib/auth";
import {
  ME,
  SEARCH_PATIENTS,
  VITALS_THRESHOLDS,
  VITAL_HISTORY,
} from "@/lib/graphql/operations";
import { useDebounce } from "@/lib/use-debounce";

type SearchRow = { id: string; patientId: string; name: string };

type Reading = {
  id: string;
  recordedAt: string;
  session: string;
  bpSystolic: number;
  bpDiastolic: number;
  pulse: number;
  temperature: string;
  spo2: number;
  weight: string | null;
  hasFlag: boolean;
  flaggedVitals: string[];
};

type Threshold = {
  vitalType: string;
  belowThreshold: string | null;
  aboveThreshold: string | null;
};

// Each vital: display label, the reading field, and the chart unit.
const VITALS = [
  { code: "BP_SYSTOLIC", label: "BP sys", field: "bpSystolic", unit: "mmHg" },
  { code: "BP_DIASTOLIC", label: "BP dia", field: "bpDiastolic", unit: "mmHg" },
  { code: "PULSE", label: "Pulse", field: "pulse", unit: "bpm" },
  { code: "TEMPERATURE", label: "Temp", field: "temperature", unit: "°F" },
  { code: "SPO2", label: "SpO₂", field: "spo2", unit: "%" },
  { code: "WEIGHT", label: "Weight", field: "weight", unit: "kg" },
] as const;

const ALL_CODES = VITALS.map((v) => v.code);

function fmt(ts: string) {
  return new Date(ts).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function VitalsHistoryPage() {
  const router = useRouter();

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data: meData, loading: meLoading } = useQuery(ME, { skip: !hasToken });
  const role = (meData as { me?: { role: string } })?.me?.role ?? "";
  const allowed = role === "ADMIN" || role === "NURSE";

  const [term, setTerm] = useState("");
  const [selected, setSelected] = useState<SearchRow | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [types, setTypes] = useState<string[]>([...ALL_CODES]);
  const [view, setView] = useState<"table" | "chart">("table");

  const debouncedTerm = useDebounce(term, 300);

  const { data: searchData } = useQuery(SEARCH_PATIENTS, {
    variables: { query: debouncedTerm.trim() },
    skip: !allowed || selected !== null || debouncedTerm.trim() === "",
  });

  const { data: thresholdData } = useQuery(VITALS_THRESHOLDS, {
    skip: !allowed,
  });
  const thresholds: Record<string, Threshold> = useMemo(() => {
    const list = (thresholdData as { vitalsThresholds?: Threshold[] })
      ?.vitalsThresholds;
    return Object.fromEntries((list ?? []).map((t) => [t.vitalType, t]));
  }, [thresholdData]);

  const { data, loading } = useQuery(VITAL_HISTORY, {
    variables: {
      patientId: selected?.id,
      dateFrom: dateFrom || null,
      dateTo: dateTo || null,
      types: types.length ? types : null,
    },
    skip: !selected || types.length === 0,
  });
  const readings: Reading[] =
    (data as { vitalHistory?: Reading[] })?.vitalHistory ?? [];

  const shownVitals = VITALS.filter((v) => types.includes(v.code));

  function toggleType(code: string) {
    setTypes((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
  }

  if (!hasToken || meLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (!allowed) {
    return (
      <main className="mx-auto min-h-screen max-w-2xl p-8">
        <Card>
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Vitals history is available to Nurse and Admin only.
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Vitals viewer</h1>

      {/* Patient selection */}
      <Card>
        <CardContent className="space-y-3 pt-6">
          {selected ? (
            <div className="flex items-center justify-between">
              <div>
                <span className="font-medium">{selected.name}</span>{" "}
                <span className="font-mono text-xs text-muted-foreground">
                  {selected.patientId}
                </span>
              </div>
              <Button variant="outline" onClick={() => setSelected(null)}>
                Change
              </Button>
            </div>
          ) : (
            <>
              <Input
                type="search"
                placeholder="Search patient by name…"
                value={term}
                onChange={(e) => setTerm(e.target.value)}
              />
              <ul className="divide-y">
                {(
                  (searchData as { searchPatients?: SearchRow[] })
                    ?.searchPatients ?? []
                ).map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className="w-full py-2 text-left hover:bg-muted/50"
                      onClick={() => {
                        setSelected(p);
                        setTerm("");
                      }}
                    >
                      {p.name}{" "}
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

      {selected ? (
        <>
          {/* Filters */}
          <Card>
            <CardContent className="space-y-4 pt-6">
              <div className="flex flex-wrap gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="from">From</Label>
                  <Input
                    id="from"
                    type="date"
                    className="w-44"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="to">To</Label>
                  <Input
                    id="to"
                    type="date"
                    className="w-44"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Vital types</Label>
                <div className="flex flex-wrap gap-2">
                  {VITALS.map((v) => (
                    <button
                      key={v.code}
                      type="button"
                      onClick={() => toggleType(v.code)}
                      className={`rounded-full border px-3 py-1 text-sm ${
                        types.includes(v.code)
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-input bg-background"
                      }`}
                    >
                      {v.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* View toggle */}
              <div className="inline-flex rounded-md border p-0.5">
                {(["table", "chart"] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setView(v)}
                    className={`rounded px-4 py-1.5 text-sm font-medium capitalize ${
                      view === v
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground"
                    }`}
                  >
                    {v} view
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Results */}
          <Card>
            <CardContent className="pt-6">
              {types.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Select at least one vital type.
                </p>
              ) : loading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : readings.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No readings for this patient and filter.
                </p>
              ) : view === "table" ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Recorded</th>
                        <th className="py-2 pr-4 font-medium">Session</th>
                        {shownVitals.map((v) => (
                          <th key={v.code} className="py-2 pr-4 font-medium">
                            {v.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {readings.map((r) => (
                        <tr key={r.id} className="border-b last:border-0">
                          <td className="py-2 pr-4 whitespace-nowrap">
                            {fmt(r.recordedAt)}
                          </td>
                          <td className="py-2 pr-4">{r.session}</td>
                          {shownVitals.map((v) => {
                            const flagged = r.flaggedVitals.includes(v.code);
                            const value = (
                              r as unknown as Record<string, string | number | null>
                            )[v.field];
                            return (
                              <td
                                key={v.code}
                                className={`py-2 pr-4 ${
                                  flagged
                                    ? "bg-red-100 font-semibold text-red-700"
                                    : ""
                                }`}
                              >
                                {value ?? "—"}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="grid gap-8 sm:grid-cols-2">
                  {shownVitals.map((v) => {
                    const t = thresholds[v.code];
                    return (
                      <VitalChart
                        key={v.code}
                        title={v.label}
                        unit={v.unit}
                        labels={readings.map((r) => fmt(r.recordedAt))}
                        values={readings.map((r) => {
                          const raw = (r as unknown as Record<string, unknown>)[
                            v.field
                          ];
                          return raw === null || raw === undefined
                            ? null
                            : Number(raw);
                        })}
                        below={t?.belowThreshold ? Number(t.belowThreshold) : null}
                        above={t?.aboveThreshold ? Number(t.aboveThreshold) : null}
                      />
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </main>
  );
}
