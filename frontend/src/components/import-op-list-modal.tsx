"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { getAccessToken } from "@/lib/auth";

// Backend origin (upload endpoints live there, not on the Next host).
const API_ORIGIN = (
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT ?? "http://localhost:8000/graphql/"
).replace(/\/graphql\/?$/, "");

type Summary = {
  total: number;
  created: number;
  duplicates: number;
  errors: Array<{ row: number; message: string }>;
};

/**
 * Upload an OP list (CSV or .xlsx) to bulk-create inquiries. Shows a per-row
 * result summary. PRO only (the caller gates on role).
 */
export function ImportOpListModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function upload(file: File) {
    setError(null);
    setSummary(null);
    setBusy(true);
    try {
      const token = getAccessToken();
      const body = new FormData();
      body.append("file", file);
      const resp = await fetch(`${API_ORIGIN}/inquiries/import`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body,
      });
      const json = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(json.error ?? `Import failed (${resp.status})`);
      }
      setSummary(json as Summary);
      if ((json as Summary).created > 0) onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Import OP list"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Import OP list</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload a CSV or Excel (.xlsx) file. Columns: <b>name</b> (required),
          phone, notes. Re-uploading the same list is safe — duplicates are
          skipped.
        </p>

        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload(file);
          }}
        />

        {summary ? (
          <div className="mt-4 space-y-2 rounded-lg border bg-muted/30 p-3 text-sm">
            <p>
              <span className="font-semibold text-green-700">
                {summary.created}
              </span>{" "}
              inquiry{summary.created === 1 ? "" : "s"} created
              {summary.duplicates > 0 ? (
                <>
                  {" · "}
                  <span className="font-semibold text-amber-700">
                    {summary.duplicates}
                  </span>{" "}
                  duplicate{summary.duplicates === 1 ? "" : "s"} skipped
                </>
              ) : null}
              {summary.errors.length > 0 ? (
                <>
                  {" · "}
                  <span className="font-semibold text-red-700">
                    {summary.errors.length}
                  </span>{" "}
                  error{summary.errors.length === 1 ? "" : "s"}
                </>
              ) : null}
            </p>
            {summary.errors.length > 0 ? (
              <ul className="max-h-40 space-y-0.5 overflow-y-auto text-xs text-red-700">
                {summary.errors.map((er) => (
                  <li key={er.row}>
                    Row {er.row}: {er.message}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}

        <div className="mt-5 flex gap-2">
          <Button
            type="button"
            variant="outline"
            className="flex-1"
            onClick={onClose}
            disabled={busy}
          >
            {summary ? "Done" : "Cancel"}
          </Button>
          <Button
            type="button"
            className="flex-1"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
          >
            {busy ? "Importing…" : summary ? "Import another" : "Choose file"}
          </Button>
        </div>
      </div>
    </div>
  );
}
