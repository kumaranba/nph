"use client";

import { useMutation } from "@apollo/client";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CREATE_INQUIRY, INQUIRIES } from "@/lib/graphql/operations";

type InquiryForm = {
  name: string;
  source: string;
  phone: string;
  notes: string;
};

const SOURCES: Array<{ value: string; label: string }> = [
  { value: "WHATSAPP", label: "WhatsApp" },
  { value: "PHONE", label: "Phone" },
  { value: "WALKIN", label: "Walk-in" },
  { value: "WEB", label: "Web" },
  { value: "REFERRAL", label: "Referral" },
  { value: "OP_CONSULT", label: "OP consult" },
  { value: "OP_IMPORT", label: "OP list" },
];

export function NewInquiryModal({ onClose }: { onClose: () => void }) {
  const { register, handleSubmit } = useForm<InquiryForm>({
    defaultValues: { name: "", source: "PHONE", phone: "", notes: "" },
  });

  const [create, { loading, error }] = useMutation(CREATE_INQUIRY, {
    refetchQueries: [{ query: INQUIRIES, variables: { status: null, search: null } }],
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

  function onSubmit(values: InquiryForm) {
    create({
      variables: {
        data: {
          name: values.name,
          source: values.source,
          phone: values.phone,
          notes: values.notes,
        },
      },
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="New inquiry"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">New inquiry</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Log a prospective patient enquiry.
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-4 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="iq-name">Name</Label>
            <Input
              id="iq-name"
              placeholder="Full name"
              {...register("name", { required: true })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="iq-source">Source</Label>
            <select
              id="iq-source"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              {...register("source", { required: true })}
            >
              {SOURCES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="iq-phone">Phone (optional)</Label>
            <Input id="iq-phone" placeholder="Mobile number" {...register("phone")} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="iq-notes">Notes (optional)</Label>
            <textarea
              id="iq-notes"
              rows={3}
              placeholder="What did they ask about?"
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              {...register("notes")}
            />
          </div>

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
              {loading ? "Saving…" : "Save inquiry"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
