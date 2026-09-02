"use client";

import { useQuery } from "@apollo/client";
import { useParams, useRouter } from "next/navigation";
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
import { QueryError, TableSkeleton } from "@/components/query-states";
import { getAccessToken } from "@/lib/auth";
import { ACCOUNT_STATEMENT, ME } from "@/lib/graphql/operations";
import { formatDate } from "@/lib/format-date";

type Line = {
  date: string;
  description: string;
  debit: string;
  credit: string;
  balance: string;
};
type AdmissionPeriod = {
  id: string;
  admissionDate: string;
  dischargeDate: string | null;
  isCurrent: boolean;
};
type Statement = {
  patientName: string;
  patientCode: string;
  admissionId: string | null;
  scopeLabel: string;
  availableAdmissions: AdmissionPeriod[];
  openingBalance: string;
  closingBalance: string;
  totalDebits: string;
  totalCredits: string;
  lines: Line[];
};

const ALL_SCOPE = "__all__";

function periodLabel(a: AdmissionPeriod, fmt: (d: string) => string): string {
  if (a.isCurrent) return `Current admission · ${fmt(a.admissionDate)} – present`;
  return `${fmt(a.admissionDate)} → ${a.dischargeDate ? fmt(a.dischargeDate) : "—"}`;
}
type StatementResult = { accountStatement: Statement };
type MeResult = { me: { role: string } };

const STATEMENT_BASE = (
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/"
).replace(/\/graphql\/?$/, "/reports/statement/");

function money(v: string | number) {
  const n = Number(v);
  return `${n < 0 ? "-" : ""}₹${Math.abs(n).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function AccountStatementPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  // Scope: null = backend default (current admission); an admission id; or ALL_SCOPE.
  const [scope, setScope] = useState<string | null>(null);

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data: meData, loading: meLoading } = useQuery<MeResult>(ME, {
    skip: !hasToken,
  });
  const allowed = meData?.me.role === "ADMIN" || meData?.me.role === "FINANCE";

  const scopedAdmissionId = scope && scope !== ALL_SCOPE ? scope : null;
  const allAdmissions = scope === ALL_SCOPE;

  const { data, loading, error, refetch } = useQuery<StatementResult>(
    ACCOUNT_STATEMENT,
    {
      variables: {
        pid: params.id,
        from: from || null,
        to: to || null,
        admissionId: scopedAdmissionId,
        allAdmissions,
      },
      skip: !hasToken || !allowed,
    }
  );
  const s = data?.accountStatement;
  // The select reflects the current default until the user picks something.
  const selectValue = scope ?? s?.admissionId ?? "";
  const showScopePicker = (s?.availableAdmissions.length ?? 0) >= 2;

  async function downloadPdf() {
    const token = getAccessToken();
    if (!token) return;
    const qs = new URLSearchParams();
    if (from) qs.set("from", from);
    if (to) qs.set("to", to);
    if (allAdmissions) qs.set("all", "1");
    else if (scopedAdmissionId) qs.set("admission", scopedAdmissionId);
    const url = `${STATEMENT_BASE}${params.id}.pdf${qs.toString() ? `?${qs}` : ""}`;
    const resp = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = `statement-${s?.patientCode ?? params.id}.pdf`;
    a.click();
    URL.revokeObjectURL(objectUrl);
  }

  if (!hasToken || meLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-4">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (!allowed) {
    return (
      <main className="mx-auto min-h-screen max-w-3xl p-4 sm:p-6 lg:p-8">
        <Card>
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
            <CardDescription>
              Account statements are available to Finance and Admin only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl p-4 sm:p-6 lg:p-8">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Account statement</CardTitle>
              <CardDescription>
                {s ? `${s.patientName} · ${s.patientCode}` : "Invoices vs payments"}
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => router.push(`/patients/${params.id}`)}
              >
                Back
              </Button>
              <Button onClick={downloadPdf} disabled={!s}>
                Download PDF
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            {showScopePicker ? (
              <div className="space-y-1.5">
                <Label htmlFor="scope">Period</Label>
                <select
                  id="scope"
                  className="h-10 w-72 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={selectValue}
                  onChange={(e) => setScope(e.target.value)}
                >
                  {s?.availableAdmissions.map((a) => (
                    <option key={a.id} value={a.id}>
                      {periodLabel(a, formatDate)}
                    </option>
                  ))}
                  <option value={ALL_SCOPE}>Full history (all admissions)</option>
                </select>
              </div>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor="from">From</Label>
              <Input
                id="from"
                type="date"
                className="w-44"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="to">To</Label>
              <Input
                id="to"
                type="date"
                className="w-44"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </div>
          </div>

          {s ? (
            <p className="text-xs text-muted-foreground">
              Showing <span className="font-medium text-foreground">{s.scopeLabel}</span>
              {s.availableAdmissions.length >= 2 && scope !== ALL_SCOPE
                ? " · earlier stays are in the Period dropdown"
                : ""}
            </p>
          ) : null}

          {loading ? (
            <TableSkeleton rows={5} cols={5} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : s ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Date</th>
                    <th className="py-2 pr-4 font-medium">Description</th>
                    <th className="py-2 pr-4 text-right font-medium">Debit</th>
                    <th className="py-2 pr-4 text-right font-medium">Credit</th>
                    <th className="py-2 text-right font-medium">Balance</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b font-medium">
                    <td className="py-2 pr-4" colSpan={4}>
                      Opening balance
                    </td>
                    <td className="py-2 text-right">{money(s.openingBalance)}</td>
                  </tr>
                  {s.lines.map((ln, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-2 pr-4 whitespace-nowrap">{formatDate(ln.date)}</td>
                      <td className="py-2 pr-4">{ln.description}</td>
                      <td className="py-2 pr-4 text-right">
                        {Number(ln.debit) ? money(ln.debit) : "—"}
                      </td>
                      <td className="py-2 pr-4 text-right">
                        {Number(ln.credit) ? money(ln.credit) : "—"}
                      </td>
                      <td className="py-2 text-right">{money(ln.balance)}</td>
                    </tr>
                  ))}
                  <tr className="border-t-2 border-foreground/60 font-semibold">
                    <td className="py-2 pr-4" colSpan={2}>
                      Closing balance
                    </td>
                    <td className="py-2 pr-4 text-right">{money(s.totalDebits)}</td>
                    <td className="py-2 pr-4 text-right">{money(s.totalCredits)}</td>
                    <td className="py-2 text-right">{money(s.closingBalance)}</td>
                  </tr>
                </tbody>
              </table>
              {Number(s.closingBalance) < 0 ? (
                <p className="mt-2 text-xs text-muted-foreground">
                  A negative balance is advance credit held on the account.
                </p>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </main>
  );
}
