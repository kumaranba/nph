"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useState } from "react";
import { useForm } from "react-hook-form";

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
import { formatDate } from "@/lib/format-date";
import {
  CREATE_FOLLOW_UP,
  DUE_FOLLOW_UP_COUNT,
  FOLLOW_UPS,
  MARK_FOLLOW_UP_DONE,
} from "@/lib/graphql/operations";

type FollowUp = {
  id: string;
  note: string;
  followUpDate: string;
  isDone: boolean;
};

type Result = { followUps: FollowUp[] };

type NewForm = { followUpDate: string; note: string };

/**
 * Follow-up reminders for one patient. Visible to PRM roles (PRO + ADMIN).
 * PRO can add reminders and mark them done; ADMIN is view-only.
 */
export function PatientFollowUpsPanel({
  patientId,
  canManage,
}: {
  patientId: string;
  canManage: boolean;
}) {
  const [showForm, setShowForm] = useState(false);
  const { register, handleSubmit, reset } = useForm<NewForm>({
    defaultValues: {
      followUpDate: new Date().toISOString().slice(0, 10),
      note: "",
    },
  });

  const { data, loading } = useQuery<Result>(FOLLOW_UPS, {
    variables: { patientId },
    fetchPolicy: "cache-and-network",
  });

  const refetchQueries = [
    { query: FOLLOW_UPS, variables: { patientId } },
    { query: DUE_FOLLOW_UP_COUNT },
  ];

  const [create, { loading: creating, error: createError }] = useMutation(
    CREATE_FOLLOW_UP,
    {
      refetchQueries,
      onCompleted: () => {
        reset();
        setShowForm(false);
      },
      onError: () => {},
    }
  );

  const [markDone, { loading: marking }] = useMutation(MARK_FOLLOW_UP_DONE, {
    refetchQueries,
    onError: () => {},
  });

  const rows = data?.followUps ?? [];
  const today = new Date().toISOString().slice(0, 10);

  function onSubmit(values: NewForm) {
    create({
      variables: {
        data: {
          patientId,
          followUpDate: values.followUpDate,
          note: values.note,
        },
      },
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>Follow-ups</CardTitle>
            <CardDescription>Scheduled reminders for this patient</CardDescription>
          </div>
          {canManage && !showForm ? (
            <Button size="sm" variant="outline" onClick={() => setShowForm(true)}>
              Add
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {canManage && showForm ? (
          <form
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-3 rounded-lg border bg-muted/30 p-3"
          >
            <div className="space-y-1.5">
              <Label htmlFor="fu-date">Date</Label>
              <Input
                id="fu-date"
                type="date"
                {...register("followUpDate", { required: true })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="fu-note">Note (optional)</Label>
              <textarea
                id="fu-note"
                rows={2}
                placeholder="What to follow up on…"
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                {...register("note")}
              />
            </div>
            {createError ? (
              <p className="text-sm text-red-600">{createError.message}</p>
            ) : null}
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="flex-1"
                onClick={() => {
                  reset();
                  setShowForm(false);
                }}
                disabled={creating}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                className="flex-1"
                disabled={creating}
              >
                {creating ? "Saving…" : "Add follow-up"}
              </Button>
            </div>
          </form>
        ) : null}

        {loading && rows.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">
            No follow-ups scheduled.
          </p>
        ) : (
          <ul className="space-y-2">
            {rows.map((r) => {
              const overdue = !r.isDone && r.followUpDate <= today;
              return (
                <li
                  key={r.id}
                  className="flex items-start justify-between gap-3 rounded-lg border p-2.5"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm">
                      <span
                        className={
                          r.isDone
                            ? "font-medium text-muted-foreground line-through"
                            : overdue
                              ? "font-semibold text-red-700"
                              : "font-medium"
                        }
                      >
                        {formatDate(r.followUpDate)}
                      </span>
                      {r.isDone ? (
                        <span className="rounded-full bg-green-50 px-1.5 text-[11px] font-semibold text-green-700">
                          Done
                        </span>
                      ) : overdue ? (
                        <span className="rounded-full bg-red-50 px-1.5 text-[11px] font-semibold text-red-700">
                          Due
                        </span>
                      ) : null}
                    </div>
                    {r.note ? (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {r.note}
                      </p>
                    ) : null}
                  </div>
                  {canManage && !r.isDone ? (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={marking}
                      onClick={() => markDone({ variables: { id: r.id } })}
                    >
                      Mark done
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
