"use client";

import { useMutation } from "@apollo/client";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  CLEAR_PLANNED_DISCHARGE_DATE,
  SET_PLANNED_DISCHARGE_DATE,
} from "@/lib/graphql/operations";
import { formatDate } from "@/lib/format-date";

// Planned discharge date for an active admission — the vacancy-forecast target.
// ADMIN can add / edit (reset) / clear it; other roles see it read-only.
export function PlannedDischargePanel({
  admissionId,
  plannedDischargeDate,
  isDischargeOverdue,
  daysUntilPlannedDischarge,
  canManage,
}: {
  admissionId: string;
  plannedDischargeDate: string | null;
  isDischargeOverdue: boolean;
  daysUntilPlannedDischarge: number | null;
  canManage: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(plannedDischargeDate ?? "");
  const today = new Date().toISOString().slice(0, 10);

  const [setDate, { loading: saving, error: saveError }] = useMutation(
    SET_PLANNED_DISCHARGE_DATE,
    { onCompleted: () => setEditing(false), onError: () => {} }
  );
  const [clearDate, { loading: clearing }] = useMutation(
    CLEAR_PLANNED_DISCHARGE_DATE,
    { onError: () => {} }
  );

  function save() {
    if (!value) return;
    setDate({ variables: { admissionId, plannedDischargeDate: value } });
  }

  const overdueNote =
    daysUntilPlannedDischarge != null && daysUntilPlannedDischarge < 0
      ? `${-daysUntilPlannedDischarge} day${
          daysUntilPlannedDischarge === -1 ? "" : "s"
        } overdue`
      : null;

  return (
    <div
      className={`rounded-lg border p-4 ${
        isDischargeOverdue ? "border-red-300 bg-red-50/60" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Planned discharge</h3>
          {plannedDischargeDate ? (
            <p className="mt-0.5 text-sm">
              {formatDate(plannedDischargeDate)}
              {isDischargeOverdue ? (
                <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
                  Discharge due{overdueNote ? ` · ${overdueNote}` : ""}
                </span>
              ) : null}
            </p>
          ) : (
            <p className="mt-0.5 text-sm text-muted-foreground">
              No discharge date planned.
            </p>
          )}
        </div>
        {canManage && !editing ? (
          <div className="flex shrink-0 gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setValue(plannedDischargeDate ?? "");
                setEditing(true);
              }}
            >
              {plannedDischargeDate
                ? isDischargeOverdue
                  ? "Reset date"
                  : "Edit"
                : "Add date"}
            </Button>
            {plannedDischargeDate ? (
              <Button
                variant="outline"
                size="sm"
                disabled={clearing}
                onClick={() => clearDate({ variables: { admissionId } })}
              >
                Clear
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>

      {canManage && editing ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            type="date"
            className="flex h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={value}
            min={today}
            onChange={(e) => setValue(e.target.value)}
          />
          <Button size="sm" disabled={saving || !value} onClick={save}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={saving}
            onClick={() => setEditing(false)}
          >
            Cancel
          </Button>
          {saveError ? (
            <p className="w-full text-sm text-red-600">{saveError.message}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
