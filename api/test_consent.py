"""Tests for contact consent / do-not-contact (R3).

RBAC: PRO sets consent on a lead or patient; ADMIN reads (via the inquiry /
patient types) but cannot set; Finance / Nurse none. Every change logs a
SYSTEM activity.
"""
import pytest

from api.models import ActivityKind, ConsentStatus, Inquiry, Patient


SET = """
mutation($consent: ConsentStatusEnum!, $dnc: Boolean!, $iid: ID, $pid: ID) {
  setContactConsent(consent: $consent, doNotContact: $dnc, inquiryId: $iid, patientId: $pid) {
    contactConsent
    doNotContact
  }
}
"""

INQUIRIES = """
query { inquiries { id contactConsent doNotContact } }
"""


@pytest.fixture
def inquiry(db):
    return Inquiry.objects.create(name="Ramesh", phone="911", source="PHONE")


@pytest.fixture
def patient(db):
    return Patient.objects.create(name="Ramesh", diagnosis="d", admitting_doctor="Dr")


def test_defaults_are_unknown_and_contactable(inquiry, patient):
    assert inquiry.contact_consent == ConsentStatus.UNKNOWN
    assert inquiry.do_not_contact is False
    assert patient.contact_consent == ConsentStatus.UNKNOWN
    assert patient.do_not_contact is False


def test_pro_sets_consent_on_lead_and_logs(pro_client, inquiry):
    result = pro_client.execute(
        SET, {"consent": "DECLINED", "dnc": True, "iid": str(inquiry.id)}
    )
    assert result.get("errors") is None
    data = result["data"]["setContactConsent"]
    assert data["contactConsent"] == "DECLINED"
    assert data["doNotContact"] is True

    inquiry.refresh_from_db()
    assert inquiry.contact_consent == ConsentStatus.DECLINED
    assert inquiry.do_not_contact is True
    # A SYSTEM activity was logged.
    assert inquiry.activities.filter(type=ActivityKind.SYSTEM).count() == 1


def test_pro_sets_consent_on_patient(pro_client, patient):
    result = pro_client.execute(
        SET, {"consent": "GRANTED", "dnc": False, "pid": str(patient.id)}
    )
    assert result.get("errors") is None
    patient.refresh_from_db()
    assert patient.contact_consent == ConsentStatus.GRANTED
    assert patient.activities.filter(type=ActivityKind.SYSTEM).count() == 1


def test_requires_a_subject(pro_client):
    result = pro_client.execute(SET, {"consent": "GRANTED", "dnc": False})
    assert result["errors"]


def test_consent_is_readable_via_inquiries(admin_client, inquiry):
    inquiry.contact_consent = ConsentStatus.DECLINED
    inquiry.do_not_contact = True
    inquiry.save()
    result = admin_client.execute(INQUIRIES, {})
    row = result["data"]["inquiries"][0]
    assert row["contactConsent"] == "DECLINED"
    assert row["doNotContact"] is True


# --- RBAC -----------------------------------------------------------------

@pytest.mark.parametrize("client_name", ["admin_client", "finance_client", "nurse_client"])
def test_set_consent_forbidden_for_non_pro(request, client_name, inquiry):
    client = request.getfixturevalue(client_name)
    result = client.execute(
        SET, {"consent": "GRANTED", "dnc": False, "iid": str(inquiry.id)}
    )
    assert result["errors"]
    inquiry.refresh_from_db()
    assert inquiry.contact_consent == ConsentStatus.UNKNOWN
