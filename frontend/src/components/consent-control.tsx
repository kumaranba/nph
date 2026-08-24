"use client";

import { useMutation } from "@apollo/client";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { SET_CONTACT_CONSENT } from "@/lib/graphql/operations";

const CONSENT_LABEL: Record<string, string> = {
  UNKNOWN: "Unknown",
  GRANTED: "Granted",
  DECLINED: "Declined",
};

/**
 * Contact-preference control for a lead or a patient: consent status + a
 * do-not-contact opt-out. PRO edits; others see a read-only summary. Renders a
 * clear "Do not contact" badge whenever the opt-out (or DECLINED) is set.
 */
export function ConsentControl({
  inquiryId,
  patientId,
  consent,
  doNotContact,
  canEdit,
  onChanged,
}: {
  inquiryId?: string;
  patientId?: string;
  consent: string;
  doNotContact: boolean;
  canEdit: boolean;
  onChanged?: () => void;
}) {
  const [value, setValue] = useState(consent);
  const [dnc, setDnc] = useState(doNotContact);
  const [save, { loading }] = useMutation(SET_CONTACT_CONSENT, {
    onCompleted: () => onChanged?.(),
    onError: () => {},
  });

  const blocked = dnc || value === "DECLINED";
  const dirty = value !== consent || dnc !== doNotContact;

  function submit() {
    save({
      variables: {
        consent: value,
        doNotContact: dnc,
        inquiryId: inquiryId ?? null,
        patientId: patientId ?? null,
      },
    });
  }

  if (!canEdit) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">
          Consent: {CONSENT_LABEL[consent] ?? consent}
        </span>
        {doNotContact ? (
          <span className="rounded-full bg-red-50 px-2 py-0.5 font-semibold text-red-700">
            Do not contact
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 p-2.5 text-xs">
      <span className="font-medium text-muted-foreground">Consent</span>
      <select
        aria-label="Contact consent"
        className="h-8 rounded-md border border-input bg-background px-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      >
        {Object.entries(CONSENT_LABEL).map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
      <label className="flex items-center gap-1.5">
        <input
          type="checkbox"
          checked={dnc}
          onChange={(e) => setDnc(e.target.checked)}
        />
        Do not contact
      </label>
      {blocked ? (
        <span className="rounded-full bg-red-50 px-2 py-0.5 font-semibold text-red-700">
          Blocked
        </span>
      ) : null}
      {dirty ? (
        <Button size="sm" className="h-8" onClick={submit} disabled={loading}>
          Save
        </Button>
      ) : null}
    </div>
  );
}
