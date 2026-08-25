"use client";

import { useMutation } from "@apollo/client";
import { MessageCircle, Phone } from "lucide-react";

import { ADD_ACTIVITY } from "@/lib/graphql/operations";
import { telLink, whatsappLink } from "@/lib/phone";

/**
 * Click-to-WhatsApp and click-to-call for a lead or patient. Opens the device's
 * WhatsApp / dialer and logs the touch as an activity. Disabled (with a reason)
 * when there's no usable number or contact is blocked (consent DECLINED or
 * do-not-contact). Render only for a PRO — logging is PRO-only.
 */
export function ContactActions({
  phone,
  inquiryId,
  patientId,
  consent,
  doNotContact,
  onLogged,
}: {
  phone: string | null | undefined;
  inquiryId?: string;
  patientId?: string;
  consent: string;
  doNotContact: boolean;
  onLogged?: () => void;
}) {
  const [log] = useMutation(ADD_ACTIVITY, {
    onCompleted: () => onLogged?.(),
    onError: () => {},
  });

  const wa = whatsappLink(phone);
  const tel = telLink(phone);
  const blocked = doNotContact || consent === "DECLINED";
  const disabled = blocked || (!wa && !tel);

  const reason = blocked
    ? "Contact blocked — do not contact"
    : "No usable phone number";

  function contact(kind: "WHATSAPP" | "CALL", href: string) {
    if (kind === "WHATSAPP") {
      window.open(href, "_blank", "noopener");
    } else {
      window.location.href = href;
    }
    log({
      variables: {
        type: kind,
        body: kind === "WHATSAPP" ? `WhatsApp opened · ${phone}` : `Called · ${phone}`,
        inquiryId: inquiryId ?? null,
        patientId: patientId ?? null,
        outcome: null,
      },
    });
  }

  const btn =
    "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium";

  if (disabled) {
    return (
      <div className="flex items-center gap-2" title={reason}>
        <span className={`${btn} cursor-not-allowed text-muted-foreground opacity-60`}>
          <MessageCircle className="h-3.5 w-3.5" aria-hidden /> WhatsApp
        </span>
        <span className={`${btn} cursor-not-allowed text-muted-foreground opacity-60`}>
          <Phone className="h-3.5 w-3.5" aria-hidden /> Call
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        disabled={!wa}
        onClick={() => wa && contact("WHATSAPP", wa)}
        className={`${btn} text-green-700 hover:bg-green-50 disabled:opacity-50`}
      >
        <MessageCircle className="h-3.5 w-3.5" aria-hidden /> WhatsApp
      </button>
      <button
        type="button"
        disabled={!tel}
        onClick={() => tel && contact("CALL", tel)}
        className={`${btn} text-blue-700 hover:bg-blue-50 disabled:opacity-50`}
      >
        <Phone className="h-3.5 w-3.5" aria-hidden /> Call
      </button>
    </div>
  );
}
