# Release notes

Notable changes to Nila IRMS, newest first. Dates are release/merge dates.

---

## v1.2 — 2026-08-20

Six sprints extend the system past patient billing into patient relationships,
staffing, and food operations. Every new figure is priced, effective-dated, and
reportable.

**At a glance:** 6 sprints · 13 feature PRs (#43–#57) · test suite grown to 661
(from ~365) · migrations through `0024` · one new role (**PRO**).

### Sprint 1 — Patient documents & demographics (#43, #44)
- Date-of-birth drives a **computed age**; the stored `age` field is retired
  (renamed `legacy_age`, kept one release for rollback).
- New patient fields: gender, food preference, and **life status**
  (`is_alive` / `date_of_expiry`).
- **Aadhar number + scan**, restricted to Admin at the API layer.
- Patient **photo** and Aadhar-scan uploads (REST, multipart, size/type checked).

### Sprint 2 — Re-admission & discharged list (#45, #46)
- **Re-admit** an existing patient — each `Admission` starts its own
  independent fee history.
- **Discharged-patient list** with tag search and discharge-date sort.

### Sprint 3 — Patient Relationship Management (#47, #48, #49)
- New **PRO** (Patient Relations Officer) role with a scoped, role-filtered
  navigation menu; PROs land on Inquiries after login.
- **Inquiries** — log, filter (status/search), advance status, and
  convert-to-patient (links the created patient).
- **Follow-ups** with a due-reminder **notification bell** (PRO + Admin).
- **OP-list import** — bulk-create inquiries from a CSV or `.xlsx` file, with
  idempotent dedup and per-row error reporting (adds `openpyxl`).
- PROs may also read the discharged-patient list (they work follow-ups off it).

### Sprint 4 — Staff attendance (#51, #52)
- **Staff registry** — a record per employee (auto `STF-NNNN` code,
  designation), independent of app logins. Deactivate, never delete.
- Daily **attendance roster**: present / absent / leave / half-day, with a
  "mark all present" shortcut and an atomic bulk save.
- Per-staff **monthly summaries**.

### Sprint 5 — Food vendor billing (#53, #55)
- An **effective-dated food rate** per patient-day — history preserved, so past
  periods stay priced at the rate then in force.
- **Vendor payment list** — daily patient-days × the day's rate.
- **Patient-wise monthly report**, grouped: discharged / newly-admitted /
  whole-month, with per-group and grand totals.
- Both reports downloadable as **PDF**.

### Sprint 6 — Canteen meal count (#56, #57)
- Adds a **gender** field to `Staff` and a configurable **monthly staff meal
  rate** (effective-dated).
- **Monthly canteen report**: daily counts split Male / Female — patients from
  admissions, staff from attendance (present/half-day). **Wednesday & Sunday**
  patient counts split Veg / Non-veg by preference; other days are Veg-only.
- Costs: patients at the daily food rate, staff at the flat monthly rate ×
  active-staff count. On-screen table + **PDF**.

### Roles at a glance
| Area | Admin | Finance | Nurse | PRO |
|---|---|---|---|---|
| Patient records & documents | full | view | view | — |
| Billing, fees & food reports | full | full | — | — |
| Vitals & clinical | full | — | full | — |
| Inquiries & follow-ups (PRM) | view | — | — | full |
| Discharged-patient list | full | full | — | full |
| Staff, attendance & canteen | full | rates only | — | — |

### Infrastructure
- CI now runs **once per commit** — the `push` trigger is scoped to `main`, so a
  PR branch no longer runs the whole workflow twice (#50).

### Upgrade / operator notes
1. Set the two rates before cost figures appear: the **food rate** on the
   *Food vendor* page and the monthly **staff meal rate** on the *Canteen* page.
2. **Backfill staff gender** — the staff list flags "gender not set"; it's what
   splits the canteen count into Male / Female.
3. Provision **PRO** users under *Users & roles*.
4. Deploy: `pip install -r requirements.txt` (adds `openpyxl`) and
   `python manage.py migrate` (through `0024`).
