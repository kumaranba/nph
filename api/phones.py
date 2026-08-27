"""Server-side phone normalization.

Mirrors the frontend ``toE164Digits`` helper (``frontend/src/lib/phone.ts``):
free-text numbers are normalized to E.164 (India +91 by default) so a number
entered on the public web-enquiry form is stored the same way a PRO's
click-to-WhatsApp / click-to-call links expect.
"""
import re

DEFAULT_CC = '91'  # India


def normalize_phone(raw, default_cc=DEFAULT_CC):
    """Normalize a free-text phone number to E.164 (``+<cc><number>``).

    Returns the normalized string when there are enough digits to be a real
    number; otherwise returns the trimmed original so a partial contact is
    never silently dropped. An empty/blank input returns ''.
    """
    if not raw:
        return ''
    trimmed = raw.strip()
    digits = re.sub(r'\D', '', trimmed)
    if len(digits) < 10:
        return trimmed
    # Drop a leading international "00" prefix (e.g. 0091…).
    if digits.startswith('00'):
        digits = digits[2:]
    # Drop a leading trunk "0" (e.g. 09876543210).
    if len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    # Bare 10-digit local number → prepend the default country code.
    if len(digits) == 10:
        digits = default_cc + digits
    return '+' + digits
