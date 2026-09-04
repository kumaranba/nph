"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ADD_BED,
  PATIENT,
  READMIT_PATIENT,
  ROOMS_WITH_BEDS,
} from "@/lib/graphql/operations";

type BedLite = { id: string; label: string; status: string };
type RoomsResult = {
  rooms: Array<{ id: string; name: string; beds: BedLite[] }>;
};

type ReadmitForm = {
  admissionDate: string;
  monthlyFee: string;
  bedId: string;
};

// Preview the next auto-incremented bed label for a room (mirrors the server).
function nextBedLabel(beds: BedLite[]): string {
  let prefix = "B";
  let highest = 0;
  let found = false;
  for (const b of beds) {
    const m = /^\s*([A-Za-z]*)\s*(\d+)\s*$/.exec(b.label ?? "");
    if (m && (!found || Number(m[2]) > highest)) {
      found = true;
      highest = Number(m[2]);
      prefix = m[1] || "B";
    }
  }
  return `${prefix}${highest + 1}`;
}

export function ReadmitModal({
  patientId,
  patientName,
  title,
  onClose,
}: {
  patientId: string;
  patientName: string;
  title: string;
  onClose: () => void;
}) {
  const { register, handleSubmit, setValue } = useForm<ReadmitForm>({
    defaultValues: {
      admissionDate: new Date().toISOString().slice(0, 10),
      monthlyFee: "",
      bedId: "",
    },
  });

  const [roomId, setRoomId] = useState("");
  const { data: roomsData, loading: roomsLoading, refetch } =
    useQuery<RoomsResult>(ROOMS_WITH_BEDS);
  const selectedRoom = roomsData?.rooms.find((r) => r.id === roomId);
  const vacantBeds =
    selectedRoom?.beds.filter((b) => b.status === "VACANT") ?? [];

  const [addBed, { loading: addingBed, error: addBedError }] = useMutation(
    ADD_BED,
    {
      onCompleted: async (data) => {
        await refetch();
        setValue("bedId", data.addBed.id);
      },
      onError: () => {},
    }
  );

  const [readmit, { loading, error }] = useMutation(READMIT_PATIENT, {
    refetchQueries: [
      { query: PATIENT, variables: { pk: patientId } },
      { query: ROOMS_WITH_BEDS },
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

  function onSubmit(values: ReadmitForm) {
    readmit({
      variables: {
        patientId,
        admissionDate: values.admissionDate,
        monthlyFee: values.monthlyFee,
        bedId: values.bedId || null,
      },
    });
  }

  const selectCls =
    "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{patientName}</p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="ra-date">Admission date</Label>
            <Input
              id="ra-date"
              type="date"
              {...register("admissionDate", { required: true })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ra-fee">Monthly fee</Label>
            <Input
              id="ra-fee"
              type="number"
              min={0}
              step="0.01"
              placeholder="0.00"
              {...register("monthlyFee", { required: true })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ra-room">Room (optional)</Label>
            <select
              id="ra-room"
              className={selectCls}
              value={roomId}
              disabled={roomsLoading}
              onChange={(e) => {
                setRoomId(e.target.value);
                setValue("bedId", "");
              }}
            >
              <option value="">Assign later (no bed)</option>
              {roomsData?.rooms.map((r) => {
                const free = r.beds.filter((b) => b.status === "VACANT").length;
                return (
                  <option key={r.id} value={r.id}>
                    {r.name} ({free} vacant)
                  </option>
                );
              })}
            </select>
          </div>
          {roomId ? (
            <div className="space-y-2">
              <Label htmlFor="ra-bed">Bed</Label>
              <select
                id="ra-bed"
                className={selectCls}
                disabled={vacantBeds.length === 0}
                {...register("bedId")}
              >
                <option value="">
                  {vacantBeds.length === 0 ? "No vacant beds" : "Select a bed"}
                </option>
                {vacantBeds.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.label}
                  </option>
                ))}
              </select>
              {vacantBeds.length === 0 && selectedRoom ? (
                <div className="space-y-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="w-full"
                    disabled={addingBed}
                    onClick={() => addBed({ variables: { roomId } })}
                  >
                    {addingBed
                      ? "Adding bed…"
                      : `Add bed ${nextBedLabel(selectedRoom.beds)} to ${selectedRoom.name}`}
                  </Button>
                  {addBedError ? (
                    <p className="text-sm text-red-600">{addBedError.message}</p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      This room is full — add a bed to admit here.
                    </p>
                  )}
                </div>
              ) : null}
            </div>
          ) : null}

          {error ? <p className="text-sm text-red-600">{error.message}</p> : null}

          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={onClose}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" className="flex-1" disabled={loading}>
              {loading ? "Admitting…" : "Admit"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
