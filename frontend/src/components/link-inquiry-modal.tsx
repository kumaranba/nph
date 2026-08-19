"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  INQUIRIES,
  LINK_INQUIRY_TO_PATIENT,
  SEARCH_PATIENTS,
} from "@/lib/graphql/operations";

type PatientHit = {
  id: string;
  patientId: string;
  name: string;
  guardianName: string | null;
};

/**
 * Convert an inquiry by linking it to an existing patient record. Admit the
 * person first (New admission), then search and pick them here — linking sets
 * the FK and flips the inquiry to CONVERTED.
 */
export function LinkInquiryModal({
  inquiryId,
  inquiryName,
  onClose,
}: {
  inquiryId: string;
  inquiryName: string;
  onClose: () => void;
}) {
  const [term, setTerm] = useState(inquiryName);

  const { data, loading: searching } = useQuery<{ searchPatients: PatientHit[] }>(
    SEARCH_PATIENTS,
    { variables: { query: term }, skip: term.trim().length < 2 }
  );

  const [link, { loading, error }] = useMutation(LINK_INQUIRY_TO_PATIENT, {
    refetchQueries: [
      { query: INQUIRIES, variables: { status: null, search: null } },
    ],
    onCompleted: onClose,
    onError: () => {},
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const hits = data?.searchPatients ?? [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Convert inquiry"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-md flex-col rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Convert to patient</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Link “{inquiryName}” to their patient record. Admit them first if they
          aren’t in the system yet.
        </p>

        <div className="mt-4 space-y-2">
          <Label htmlFor="li-search">Find patient</Label>
          <Input
            id="li-search"
            autoFocus
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder="Name or patient ID…"
          />
        </div>

        <div className="mt-3 min-h-0 flex-1 overflow-y-auto">
          {term.trim().length < 2 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Type at least 2 characters to search.
            </p>
          ) : searching ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Searching…
            </p>
          ) : hits.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No matching patients.
            </p>
          ) : (
            <ul className="divide-y">
              {hits.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() =>
                      link({ variables: { id: inquiryId, patientId: p.id } })
                    }
                    className="flex w-full items-center justify-between gap-3 py-2.5 text-left hover:bg-accent/50 disabled:opacity-50"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        {p.name}
                      </span>
                      <span className="block font-mono text-xs text-muted-foreground">
                        {p.patientId}
                        {p.guardianName ? ` · ${p.guardianName}` : ""}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs font-medium text-primary">
                      Link →
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {error ? (
          <p className="mt-2 text-sm text-red-600">{error.message}</p>
        ) : null}

        <div className="mt-4">
          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={onClose}
            disabled={loading}
          >
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
