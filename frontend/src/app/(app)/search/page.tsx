"use client";

import { useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  EmptyState,
  QueryError,
  TableSkeleton,
} from "@/components/query-states";
import { getAccessToken } from "@/lib/auth";
import { SEARCH_PATIENTS } from "@/lib/graphql/operations";
import { useDebounce } from "@/lib/use-debounce";

type SearchRow = {
  id: string;
  patientId: string;
  name: string;
  guardianName: string;
  guardianPhone: string;
  admissionDate: string | null;
  room: string | null;
  bed: string | null;
  feeStatus: "CURRENT" | "DUE_SOON" | "OVERDUE";
};

type SearchResult = { searchPatients: SearchRow[] };

const FEE_BADGE: Record<
  SearchRow["feeStatus"],
  { label: string; className: string }
> = {
  CURRENT: { label: "Current", className: "bg-green-100 text-green-800" },
  DUE_SOON: { label: "Due Soon", className: "bg-amber-100 text-amber-800" },
  OVERDUE: { label: "Overdue", className: "bg-red-100 text-red-800" },
};

function FeeBadge({ status }: { status: SearchRow["feeStatus"] }) {
  const badge = FEE_BADGE[status];
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}
    >
      {badge.label}
    </span>
  );
}

export default function SearchPage() {
  const router = useRouter();
  const [term, setTerm] = useState("");
  const debouncedTerm = useDebounce(term, 300); // 300ms debounce

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const trimmed = debouncedTerm.trim();
  const { data, loading, error, refetch } = useQuery<SearchResult>(
    SEARCH_PATIENTS,
    {
      variables: { query: trimmed },
      skip: !hasToken || trimmed === "",
    }
  );

  if (!hasToken) return null;

  const rows = data?.searchPatients ?? [];
  const showEmpty = trimmed !== "" && !loading && !error && rows.length === 0;

  return (
    <main className="mx-auto min-h-screen max-w-3xl p-8">
      <Card>
        <CardHeader>
          <CardTitle>Search patients</CardTitle>
          <CardDescription>
            Search by name, patient ID, or guardian name / phone
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            type="search"
            autoFocus
            placeholder="Start typing to search…"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
          />

          {trimmed === "" ? (
            <EmptyState
              title="Search for a patient"
              description="Enter a name, patient ID, or guardian name / phone above."
            />
          ) : loading ? (
            <TableSkeleton rows={4} cols={5} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : showEmpty ? (
            <EmptyState
              title="No matches"
              description={`No patients match “${trimmed}”.`}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Patient</th>
                    <th className="py-2 pr-4 font-medium">Patient ID</th>
                    <th className="py-2 pr-4 font-medium">Bed</th>
                    <th className="py-2 pr-4 font-medium">Admitted</th>
                    <th className="py-2 font-medium">Fee status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.id}
                      className="cursor-pointer border-b last:border-0 hover:bg-muted/50"
                      onClick={() => router.push(`/patients/${row.id}`)}
                    >
                      <td className="py-2 pr-4">{row.name}</td>
                      <td className="py-2 pr-4 font-mono text-xs">
                        {row.patientId}
                      </td>
                      <td className="py-2 pr-4">
                        {row.room && row.bed
                          ? `${row.room} · ${row.bed}`
                          : "—"}
                      </td>
                      <td className="py-2 pr-4">{row.admissionDate ?? "—"}</td>
                      <td className="py-2">
                        <FeeBadge status={row.feeStatus} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
