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
import { TagChip, TagInput } from "@/components/tag-input";
import {
  EmptyState,
  QueryError,
  TableSkeleton,
} from "@/components/query-states";
import { getAccessToken } from "@/lib/auth";
import { PATIENTS_BY_TAGS, SEARCH_PATIENTS } from "@/lib/graphql/operations";
import { useDebounce } from "@/lib/use-debounce";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format-date";

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
  tags: string[];
};

type SearchResult = { searchPatients: SearchRow[] };
type TagSearchResult = { patientsByTags: SearchRow[] };

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
  const [tags, setTags] = useState<string[]>([]);
  const [match, setMatch] = useState<"ANY" | "ALL">("ANY");
  const debouncedTerm = useDebounce(term, 300); // 300ms debounce

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  // Tag filter takes precedence; otherwise fall back to text search.
  const byTags = tags.length > 0;
  const trimmed = debouncedTerm.trim();

  const textQuery = useQuery<SearchResult>(SEARCH_PATIENTS, {
    variables: { query: trimmed },
    skip: !hasToken || byTags || trimmed === "",
  });
  const tagQuery = useQuery<TagSearchResult>(PATIENTS_BY_TAGS, {
    variables: { tags, match },
    skip: !hasToken || !byTags,
  });

  if (!hasToken) return null;

  const active = byTags ? tagQuery : textQuery;
  const { loading, error, refetch } = active;
  const rows: SearchRow[] = byTags
    ? tagQuery.data?.patientsByTags ?? []
    : textQuery.data?.searchPatients ?? [];

  const hasCriteria = byTags || trimmed !== "";
  const showEmpty = hasCriteria && !loading && !error && rows.length === 0;

  function addTag(label: string) {
    setTags((prev) =>
      prev.some((t) => t.toLowerCase() === label.toLowerCase())
        ? prev
        : [...prev, label]
    );
  }
  function removeTag(label: string) {
    setTags((prev) => prev.filter((t) => t !== label));
  }

  return (
    <main className="mx-auto min-h-screen max-w-3xl p-4 sm:p-6 lg:p-8">
      <Card>
        <CardHeader>
          <CardTitle>Search patients</CardTitle>
          <CardDescription>
            Search by name, patient ID, guardian, or filter by tags
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

          {/* Tag filter */}
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-muted-foreground">
                Filter by tags
              </span>
              {tags.length > 1 ? (
                <div className="inline-flex overflow-hidden rounded-md border text-xs">
                  {(["ANY", "ALL"] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setMatch(m)}
                      className={cn(
                        "px-2.5 py-1 font-medium",
                        match === m
                          ? "bg-primary text-primary-foreground"
                          : "bg-background text-muted-foreground hover:bg-accent/60"
                      )}
                    >
                      {m === "ANY" ? "Match any" : "Match all"}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            {tags.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {tags.map((t) => (
                  <TagChip key={t} label={t} onRemove={() => removeTag(t)} />
                ))}
              </div>
            ) : null}
            <TagInput
              exclude={tags}
              allowCreate={false}
              placeholder="Add a tag to filter…"
              onSelect={addTag}
            />
          </div>

          {!hasCriteria ? (
            <EmptyState
              title="Search for a patient"
              description="Enter a name, patient ID, or guardian — or filter by tags above."
            />
          ) : loading ? (
            <TableSkeleton rows={4} cols={5} />
          ) : error ? (
            <QueryError message={error.message} onRetry={() => refetch()} />
          ) : showEmpty ? (
            <EmptyState
              title="No matches"
              description={
                byTags
                  ? `No patients match the selected tag${tags.length > 1 ? "s" : ""}.`
                  : `No patients match “${trimmed}”.`
              }
            />
          ) : (
            <>
              {/* Mobile: stacked cards */}
              <div className="space-y-2.5 sm:hidden">
                {rows.map((row) => (
                  <button
                    key={row.id}
                    type="button"
                    onClick={() => router.push(`/patients/${row.id}`)}
                    className="flex w-full items-start justify-between gap-3 rounded-lg border bg-card p-3 text-left active:bg-muted/50"
                  >
                    <div className="min-w-0">
                      <div className="font-medium">{row.name}</div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {row.patientId}
                      </div>
                      <div className="mt-1.5 text-xs text-muted-foreground">
                        {row.room && row.bed
                          ? `${row.room} · ${row.bed}`
                          : "Not admitted"}
                        {row.admissionDate ? ` · ${formatDate(row.admissionDate)}` : ""}
                      </div>
                      {row.tags.length > 0 ? (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {row.tags.map((t) => (
                            <TagChip key={t} label={t} />
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <FeeBadge status={row.feeStatus} />
                  </button>
                ))}
              </div>

              {/* Tablet/desktop: table */}
              <div className="hidden overflow-x-auto sm:block">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Patient</th>
                      <th className="py-2 pr-4 font-medium">Patient ID</th>
                      <th className="py-2 pr-4 font-medium">Bed</th>
                      <th className="py-2 pr-4 font-medium">Tags</th>
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
                        <td className="py-2 pr-4">
                          {row.tags.length > 0 ? (
                            <span className="flex flex-wrap gap-1">
                              {row.tags.map((t) => (
                                <TagChip key={t} label={t} />
                              ))}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="py-2">
                          <FeeBadge status={row.feeStatus} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
