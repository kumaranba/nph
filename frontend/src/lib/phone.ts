// Phone-number helpers for click-to-WhatsApp / click-to-call.
// Numbers are normalized to E.164 (India +91 by default) so wa.me and tel:
// links work regardless of how the number was entered.

const DEFAULT_CC = "91"; // India

/**
 * Normalize a free-text phone number to E.164 digits (country code + number,
 * no "+"). Returns null when there aren't enough digits to be a real number.
 */
export function toE164Digits(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let digits = raw.replace(/\D/g, "");
  if (digits.length < 10) return null;
  // Drop a leading trunk "0" (e.g. 09876543210).
  if (digits.length === 11 && digits.startsWith("0")) {
    digits = digits.slice(1);
  }
  // Bare 10-digit local number → prepend the default country code.
  if (digits.length === 10) {
    digits = DEFAULT_CC + digits;
  }
  return digits;
}

/** wa.me chat link for a number, or null if it can't be normalized. */
export function whatsappLink(raw: string | null | undefined): string | null {
  const d = toE164Digits(raw);
  return d ? `https://wa.me/${d}` : null;
}

/** tel: link for a number, or null if it can't be normalized. */
export function telLink(raw: string | null | undefined): string | null {
  const d = toE164Digits(raw);
  return d ? `tel:+${d}` : null;
}
