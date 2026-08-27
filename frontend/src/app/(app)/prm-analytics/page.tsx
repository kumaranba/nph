"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { QueryError, LinesSkeleton } from "@/components/query-states";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getAccessToken } from "@/lib/auth";
import { PRM_ANALYTICS } from "@/lib/graphql/operations";
import { useMe } from "@/lib/me-context";

type SourceStat = {
  source: string;
  leads: number;
  converted: number;
  conversionRate: number;
};
type Analytics = {
  totalLeads: number;
  converted: number;
  lost: number;
  open: number;
  conversionRate: number;
  avgDaysToConvert: number | null;
  bySource: SourceStat[];
  byStage: Array<{ stage: string; count: number }>;
  lostReasons: Array<{ reason: string; count: number }>;
  monthly: Array<{ month: string; leads: number }>;
  byPro: Array<{ email: string; owned: number; converted: number }>;
};
type Result = { prmAnalytics: Analytics };

const SOURCE_LABEL: Record<string, string> = {
  WHATSAPP: "WhatsApp",
  PHONE: "Phone",
  WALKIN: "Walk-in",
  WEB: "Web",
  REFERRAL: "Referral",
  OP_CONSULT: "OP consult",
  OP_IMPORT: "OP list",
};
const STAGE_LABEL: Record<string, string> = {
  NEW: "New",
  CONTACTED: "Contacted",
  CONSULTED: "Consulted",
  ADMITTED: "Admitted",
  LOST: "Lost",
};

const pct = (n: number) => `${Math.round(n * 100)}%`;
const monthLabel = (m: string) => {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1).toLocaleString("en-IN", { month: "short" });
};

export default function PrmAnalyticsPage() {
  const router = useRouter();
  const me = useMe();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const allowed = me?.role === "PRO" || me?.role === "ADMIN";
  const { data, loading, error, refetch } = useQuery<Result>(PRM_ANALYTICS, {
    variables: { dateFrom: from || null, dateTo: to || null },
    skip: !hasToken || !allowed,
    fetchPolicy: "cache-and-network",
  });

  if (!hasToken) {
    return (
      <main className="flex min-h-screen items-center justify-center p-4">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }
  if (me && !allowed) {
    return (
      <main className="mx-auto min-h-screen max-w-3xl p-4 sm:p-6 lg:p-8">
        <Card>
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
            <CardDescription>
              PRM analytics are available to Patient Relations and Admin only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  const a = data?.prmAnalytics;
  const maxSource = Math.max(1, ...(a?.bySource.map((s) => s.leads) ?? [1]));
  const maxMonth = Math.max(1, ...(a?.monthly.map((m) => m.leads) ?? [1]));
  const maxStage = Math.max(1, ...(a?.byStage.map((s) => s.count) ?? [1]));

  const tiles = a
    ? [
        { label: "Total leads", value: a.totalLeads },
        { label: "Converted", value: a.converted, sub: pct(a.conversionRate) },
        { label: "Open", value: a.open },
        { label: "Lost", value: a.lost },
        {
          label: "Avg days to convert",
          value: a.avgDaysToConvert == null ? "—" : Math.round(a.avgDaysToConvert),
        },
      ]
    : [];

  return (
    <main className="mx-auto min-h-screen max-w-4xl space-y-5 p-4 sm:p-6 lg:p-8">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <CardTitle>PRM analytics</CardTitle>
              <CardDescription>Inquiry pipeline and conversion</CardDescription>
            </div>
            <div className="flex items-end gap-2">
              <label className="space-y-1 text-xs">
                <span className="block text-muted-foreground">From</span>
                <Input
                  type="date"
                  value={from}
                  max={to || undefined}
                  onChange={(e) => setFrom(e.target.value)}
                  className="h-9"
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="block text-muted-foreground">To</span>
                <Input
                  type="date"
                  value={to}
                  min={from || undefined}
                  onChange={(e) => setTo(e.target.value)}
                  className="h-9"
                />
              </label>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading && !a ? (
            <LinesSkeleton lines={4} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : !a ? null : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
              {tiles.map((t) => (
                <div key={t.label} className="rounded-lg border bg-muted/30 p-3">
                  <div className="text-[11px] text-muted-foreground">{t.label}</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums">
                    {t.value}
                    {"sub" in t && t.sub ? (
                      <span className="ml-1 text-xs font-normal text-green-700">
                        {t.sub}
                      </span>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {a ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Conversion by source</CardTitle>
              <CardDescription>Which channels actually convert</CardDescription>
            </CardHeader>
            <CardContent>
              {a.bySource.length === 0 ? (
                <p className="text-sm text-muted-foreground">No leads yet.</p>
              ) : (
                <div className="space-y-2.5">
                  {a.bySource.map((s) => (
                    <div key={s.source}>
                      <div className="flex justify-between text-sm">
                        <span>{SOURCE_LABEL[s.source] ?? s.source}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {s.converted}/{s.leads} ·{" "}
                          <span className="font-medium text-foreground">
                            {pct(s.conversionRate)}
                          </span>
                        </span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full bg-primary/70"
                          style={{ width: `${(s.leads / maxSource) * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Pipeline stages</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {a.byStage.map((s) => (
                    <div key={s.stage} className="flex items-center gap-3">
                      <span className="w-20 shrink-0 text-sm">
                        {STAGE_LABEL[s.stage] ?? s.stage}
                      </span>
                      <div className="h-4 flex-1 overflow-hidden rounded bg-muted">
                        <div
                          className="h-full bg-primary/60"
                          style={{ width: `${(s.count / maxStage) * 100}%` }}
                        />
                      </div>
                      <span className="w-8 text-right text-sm tabular-nums">
                        {s.count}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Lost reasons</CardTitle>
              </CardHeader>
              <CardContent>
                {a.lostReasons.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No lost leads.</p>
                ) : (
                  <ul className="space-y-1.5 text-sm">
                    {a.lostReasons.map((r) => (
                      <li key={r.reason} className="flex justify-between">
                        <span>{r.reason}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {r.count}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Lead volume</CardTitle>
              <CardDescription>Last 6 months</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-end gap-3" style={{ height: 120 }}>
                {a.monthly.map((m) => (
                  <div key={m.month} className="flex flex-1 flex-col items-center gap-1">
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {m.leads}
                    </span>
                    <div
                      className="w-full rounded-t bg-primary/60"
                      style={{ height: `${(m.leads / maxMonth) * 90}px` }}
                    />
                    <span className="text-xs text-muted-foreground">
                      {monthLabel(m.month)}
                    </span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {a.byPro.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>By officer</CardTitle>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">PRO</th>
                      <th className="py-2 pr-4 text-right font-medium">Owned</th>
                      <th className="py-2 text-right font-medium">Converted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {a.byPro.map((p) => (
                      <tr key={p.email} className="border-b last:border-0">
                        <td className="py-2 pr-4">{p.email.split("@")[0]}</td>
                        <td className="py-2 pr-4 text-right tabular-nums">
                          {p.owned}
                        </td>
                        <td className="py-2 text-right tabular-nums">
                          {p.converted}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
