"""RBAC audit: hit every GraphQL query/mutation as each of the three roles and
assert the correct allow/deny outcome.

For each operation we send a document with dummy-but-valid arguments so the
request passes GraphQL validation and reaches the permission check. "Allowed"
means the response contains no "Permission denied" error (it may still fail
with a domain error such as "not found" — that's fine). "Denied" means a
"Permission denied" error is present.

Auth mutations (login/refreshToken) are intentionally excluded — they are
public by design.
"""
import pytest

ALL = {"ADMIN", "FINANCE", "NURSE", "PRO"}

# name, document, allowed_roles
OPERATIONS = [
    # --- Queries: any authenticated role ----------------------------------
    ("me", "{ me { id } }", ALL),
    ("rooms", "{ rooms { id } }", ALL),
    ("beds", "{ beds { id } }", ALL),
    ("patients", "{ patients { id } }", ALL),
    ("patient", '{ patient(pk: "1") { id } }', ALL),
    ("searchPatients", '{ searchPatients(query: "x") { id } }', ALL),
    ("admissions", "{ admissions { id } }", ALL),
    ("admission", '{ admission(pk: "1") { id } }', ALL),
    ("additionalCharges", "{ additionalCharges { id } }", ALL),
    ("vitalsThresholds", "{ vitalsThresholds { id } }", ALL),
    # --- Queries: ADMIN only ----------------------------------------------
    ("users", "{ users { id } }", {"ADMIN"}),
    ("systemSettings", "{ systemSettings { feeDueWarningDays } }", {"ADMIN"}),
    # --- Queries: ADMIN + PRO (PRM) ---------------------------------------
    ("inquiries", "{ inquiries { id } }", {"ADMIN", "PRO"}),
    # --- Queries: ADMIN + FINANCE -----------------------------------------
    ("invoices", "{ invoices { id } }", {"ADMIN", "FINANCE"}),
    ("payments", "{ payments { id } }", {"ADMIN", "FINANCE"}),
    ("invoice", '{ invoice(patientId: "1", period: "2026-01") { id } }', {"ADMIN", "FINANCE"}),
    ("invoiceList", '{ invoiceList(patientId: "1") { id } }', {"ADMIN", "FINANCE"}),
    ("feesDueList", "{ feesDueList { id } }", {"ADMIN", "FINANCE"}),
    ("feeHistory", '{ feeHistory(patientId: "1") { id } }', {"ADMIN", "FINANCE"}),
    # --- Queries: ADMIN + NURSE -------------------------------------------
    ("vitalReadings", "{ vitalReadings { id } }", {"ADMIN", "NURSE"}),
    ("vitalHistory", '{ vitalHistory(patientId: "1") { id } }', {"ADMIN", "NURSE"}),
    ("flaggedVitals", "{ flaggedVitals { id } }", {"ADMIN", "NURSE"}),
    # --- Dashboard queries ------------------------------------------------
    ("dashboardStats", "{ dashboardStats { bedsTotal } }", ALL),
    ("recentAdmissions", "{ recentAdmissions { id } }", ALL),
    ("wards", "{ wards { id } }", ALL),
    ("activityLog", "{ activityLog { id } }", ALL),
    ("paymentsTrend", "{ paymentsTrend { month } }", {"ADMIN", "FINANCE"}),
    # --- Mutations: ADMIN only --------------------------------------------
    (
        "createAdmission",
        'mutation { createAdmission(input: {name: "x", diagnosis: "d",'
        ' admittingDoctor: "dr", bedId: "1", admissionDate: "2026-01-01",'
        ' monthlyFee: "1"}) { id } }',
        {"ADMIN"},
    ),
    (
        "createUser",
        'mutation { createUser(email: "audit-new@nph.test", password: "password123",'
        " role: NURSE) { id } }",
        {"ADMIN"},
    ),
    ("deactivateUser", 'mutation { deactivateUser(userId: "999999") { id } }', {"ADMIN"}),
    ("updateSettings", "mutation { updateSettings(feeDueWarningDays: 7) { feeDueWarningDays } }", {"ADMIN"}),
    # --- Mutations: ADMIN + FINANCE ---------------------------------------
    (
        "recordPayment",
        'mutation { recordPayment(invoiceId: "1", amount: "1", paidOn: "2026-01-01") { id } }',
        {"ADMIN", "FINANCE"},
    ),
    (
        "dischargePatient",
        'mutation { dischargePatient(admissionId: "1") { hasOutstandingDues } }',
        {"ADMIN", "FINANCE"},
    ),
    (
        "recordPatientPayment",
        'mutation { recordPatientPayment(patientId: "1", feesAmount: "1", paidOn: "2026-01-01")'
        " { invoicesPaid } }",
        {"ADMIN", "FINANCE"},
    ),
    # --- Mutations: ADMIN + FINANCE (payments/refunds) --------------------
    (
        "logPayment",
        'mutation { logPayment(invoiceId: "1", amount: "1", paidOn: "2026-01-01") { id } }',
        {"ADMIN", "FINANCE"},
    ),
    (
        "logRefund",
        'mutation { logRefund(invoiceId: "1", amount: "1") { id } }',
        {"ADMIN", "FINANCE"},
    ),
    # --- Mutations: FINANCE only ------------------------------------------
    (
        "createCharge",
        'mutation { createCharge(admissionId: "1", category: DRUGS, amount: "1",'
        ' chargeDate: "2026-01-01") { id } }',
        {"FINANCE"},
    ),
    ("deleteCharge", 'mutation { deleteCharge(chargeId: "1") }', {"FINANCE"}),
    (
        "changeFee",
        'mutation { changeFee(admissionId: "1", amount: "1", reason: "r") { id } }',
        {"FINANCE"},
    ),
    # --- Mutations: ADMIN + NURSE -----------------------------------------
    (
        "createVitalReading",
        'mutation { createVitalReading(admissionId: "1", session: AM, bpSystolic: 120,'
        ' bpDiastolic: 80, pulse: 70, temperature: "98.6", spo2: 98) { id } }',
        {"ADMIN", "NURSE"},
    ),
    # --- Mutations: PRO only (PRM) ----------------------------------------
    (
        "createInquiry",
        'mutation { createInquiry(data: {name: "x", source: PHONE}) { id } }',
        {"PRO"},
    ),
    (
        "updateInquiryStatus",
        'mutation { updateInquiryStatus(inquiryId: "999999", status: CLOSED) { id } }',
        {"PRO"},
    ),
    (
        "linkInquiryToPatient",
        'mutation { linkInquiryToPatient(inquiryId: "999999", patientId: "1") { id } }',
        {"PRO"},
    ),
]


@pytest.fixture
def clients(admin_client, finance_client, nurse_client, pro_client):
    return {
        "ADMIN": admin_client,
        "FINANCE": finance_client,
        "NURSE": nurse_client,
        "PRO": pro_client,
    }


@pytest.mark.parametrize("role", ["ADMIN", "FINANCE", "NURSE", "PRO"])
@pytest.mark.parametrize(
    "name, document, allowed",
    OPERATIONS,
    ids=[op[0] for op in OPERATIONS],
)
def test_rbac_matrix(clients, role, name, document, allowed):
    result = clients[role].execute(document)
    messages = " ".join(
        e.get("message", "") for e in (result.get("errors") or [])
    )
    denied = "Permission denied" in messages

    if role in allowed:
        assert not denied, f"{name}: {role} should be ALLOWED but was denied ({messages})"
    else:
        assert denied, f"{name}: {role} should be DENIED but was not ({messages or 'no error'})"
