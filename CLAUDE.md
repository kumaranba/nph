# NPH — project notes for Claude

Django 5 + Strawberry GraphQL backend (`api` app) and a Next.js frontend.
There is no separate `billing` app — billing/fees live in the `api` app.

## Fee invariant

The `Fee` model is the source of truth for an admission's billable rate. These
invariants MUST hold and are covered by tests:

1. **Every Invoice references exactly one Fee** (`Invoice.fee` is non-null). The
   fee is snapshotted onto the invoice at generation time.
2. **Every ACTIVE admission has exactly one active Fee** (`is_active=True`).
3. **Every DISCHARGED admission has zero active Fees.**
4. **Fee rows are never deleted.** A fee change deactivates the current active
   Fee (`is_active=False`, `deactivated_at=now`) and creates a new active Fee —
   preserving full history.
5. **Only FINANCE may change a fee.** ADMIN is view-only (can read
   `feeHistory`, cannot call `changeFee`). NURSE has no access.
6. **`change_fee.effective_from` defaults** to the admission's next
   not-yet-invoiced billing cycle date. An explicit `effective_from` that
   differs from that default requires `override=True`.
7. **Generated invoices are immutable w.r.t. fees.** Changing a fee after an
   invoice is generated never alters that invoice's `base_fee` or `fee`.
8. **A re-admission is independent.** A new `Admission` row starts its own Fee
   history, unrelated to any prior admission of the same patient.

`FeeService` (`api/fees.py`) enforces these; `python manage.py
verify_fee_migration` checks 1–3 against the live database.
