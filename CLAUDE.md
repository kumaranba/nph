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

## Opening balance (imported carry-forward)

Patients migrated from the paper register (`import_register`) arrive with a
current outstanding (the `Fees Status` column). It is stored on
`Admission.opening_balance` and seeded as a single **opening-balance invoice**
(`Invoice.is_opening_balance=True`) so it flows through outstanding totals,
payment allocation (oldest-first, so it's paid down before new months),
discharge warnings, and the fees-due list like any other debt.

Rules that MUST hold (covered by tests):

1. **No double counting at import.** The opening balance is the net owed as of
   `Admission.opening_balance_as_of`. `import_register` does **not** generate a
   current-cycle invoice — the opening balance already covers everything through
   that date.
2. **Billing resumes at the next cycle.** `generate_invoice_for_admission`
   skips any monthly period whose start is `<= opening_balance_as_of`, so the
   already-covered in-progress period is never billed twice. Monthly billing
   (same day-of-month) continues normally from the first cycle after that date.
3. **The opening-balance invoice is distinguished, not a monthly bill.** It has
   `base_fee=0`, `total_due=opening_balance`, and a sentinel period (the day
   before admission) so it sorts oldest and never collides with a real period.
4. **`opening_balance_as_of` is null for non-imported admissions**, which bill
   normally from `admission_date`.

The fees-due list keeps the upcoming cycle (`amountDue`) and the carried
`openingBalance` as **separate** fields (`totalDueNow = amountDue +
openingBalance`) so the same money is never summed into two places.

## Scheduled billing (Celery)

Monthly invoices are created by `BillingService.generate_all_due_invoices`,
which is **idempotent** (skips periods already invoiced). It is driven two ways:

- **Celery Beat** runs the `api.tasks.generate_due_invoices` task **daily at
  09:00 Asia/Kolkata** (`CELERY_BEAT_SCHEDULE` in settings). This is the
  production mechanism — a started cycle's invoice appears by 09:00, so pending
  dues / fees-due stay current without any generate-on-read side effects.
- `python manage.py generate_invoices` for manual runs / backfill.

Local dev needs Redis plus two processes: `celery -A config worker` and
`celery -A config beat` (exactly one beat instance).

## Additional charges

Additional charges (drugs, snacks, specialist…) are **billed the moment they're
added** — `create_charge` calls `BillingService.bill_charge`, which:

1. **Tops up the charge's monthly invoice** (recomputes `total_due =
   base_fee + period charges`). If that invoice was already PAID, it reopens to
   PARTIAL — the patient now owes the charge.
2. For a period **covered by the opening balance** (imported patients), bills
   the charge on a **charges-only settlement invoice** (`Invoice.is_settlement`,
   `base_fee=0`) so it isn't stranded.
3. At **discharge**, `sweep_unbilled_charges` bills anything still unreflected —
   the last chance, since no invoices are generated after discharge.

Rules: a charge's `charge_date` can't be in the future; `delete_charge` reverses
the top-up and is blocked once the invoice is PAID. The account statement
**itemizes** each charge as its own debit line (fee line + one line per charge).
`python manage.py bill_pending_charges` (idempotent) sweeps historical stranded
charges.
