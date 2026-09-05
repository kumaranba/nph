"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatDate } from "@/lib/format-date";
import {
  END_PERMISSION,
  PATIENTS_ON_PERMISSION,
  PERMISSIONS,
  START_PERMISSION,
} from "@/lib/graphql/operations";

type Permission = {
  id: string;
  startDate: string;
  expectedReturn: string | null;
  returnDate: string | null;
  note: string;
  isOut: boolean;
};
type Result = { permissions: Permission[] };

const todayStr = () => new Date().toISOString().slice(0, 10);

// Permission (home-leave) control for a patient's active admission. Any role
// sees the current status; only ADMIN can record or close a permission.
export function PatientPermissionPanel({
  admissionId,
  canManage,
}: {
  admissionId: string;
  canManage: boolean;
}) {
  const [showForm, setShowForm] = useState(false);
  const [startDate, setStartDate] = useState(todayStr());
  const [expectedReturn, setExpectedReturn] = useState("");
  const [note, setNote] = useState("");

  const { data } = useQuery<Result>(PERMISSIONS, {
    variables: { admissionId },
    fetchPolicy: "cache-and-network",
  });

  const refetchAll = [
    { query: PERMISSIONS, variables: { admissionId } },
    { query: PATIENTS_ON_PERMISSION },
  ];

  const [start, { loading: starting, error: startError }] = useMutation(
    START_PERMISSION,
    {
      refetchQueries: refetchAll,
      onCompleted: () => {
        setShowForm(false);
        setExpectedReturn("");
        setNote("");
        setStartDate(todayStr());
      },
      onError: () => {},
    }
  );
  const [end, { loading: ending }] = useMutation(END_PERMISSION, {
    refetchQueries: refetchAll,
    onError: () => {},
  });

  const open = data?.permissions.find((p) => p.isOut) ?? null;

  return (
    <div className="rounded-lg border p-3">
      {open ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
              On permission
            </span>
            <span className="text-sm text-muted-foreground">
              since {formatDate(open.startDate)}
              {open.expectedReturn
                ? ` · expected back ${formatDate(open.expectedReturn)}`
                : ""}
            </span>
          </div>
          {open.note ? (
            <p className="text-xs text-muted-foreground">{open.note}</p>
          ) : null}
          {canManage ? (
            <Button
              size="sm"
              variant="outline"
              disabled={ending}
              onClick={() =>
                end({ variables: { permissionId: open.id, returnDate: todayStr() } })
              }
            >
              {ending ? "Saving…" : "Mark returned"}
            </Button>
          ) : null}
        </div>
      ) : !canManage ? (
        <p className="text-sm text-muted-foreground">Not on permission.</p>
      ) : showForm ? (
        <div className="space-y-3">
          <p className="text-sm font-medium">Record permission (home leave)</p>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="perm-start">From</Label>
              <Input
                id="perm-start"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="perm-exp">Expected back (optional)</Label>
              <Input
                id="perm-exp"
                type="date"
                min={startDate}
                value={expectedReturn}
                onChange={(e) => setExpectedReturn(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="perm-note">Note (optional)</Label>
            <Input
              id="perm-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          {startError ? (
            <p className="text-xs text-red-600">{startError.message}</p>
          ) : null}
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={starting || !startDate}
              onClick={() =>
                start({
                  variables: {
                    admissionId,
                    startDate,
                    expectedReturn: expectedReturn || null,
                    note: note || null,
                  },
                })
              }
            >
              {starting ? "Saving…" : "Record"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowForm(false)}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-muted-foreground">Not on permission.</span>
          <Button size="sm" variant="outline" onClick={() => setShowForm(true)}>
            Record permission
          </Button>
        </div>
      )}
    </div>
  );
}
