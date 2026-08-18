"""Tests for the PRM inquiry API — CRUD + RBAC.

RBAC contract: PRO manages inquiries fully; ADMIN is view-only (may read the
`inquiries` list but not create/update/link); FINANCE and NURSE have no access.
"""
import pytest

from api.models import Inquiry, InquiryStatus, Patient


CREATE = """
mutation($data: CreateInquiryInput!) {
  createInquiry(data: $data) {
    id name phone source status notes createdBy { email }
  }
}
"""

INQUIRIES = """
query($status: InquiryStatusEnum, $search: String) {
  inquiries(status: $status, search: $search) {
    id name phone status source patient { id }
  }
}
"""

UPDATE_STATUS = """
mutation($id: ID!, $status: InquiryStatusEnum!) {
  updateInquiryStatus(inquiryId: $id, status: $status) { id status }
}
"""

LINK = """
mutation($id: ID!, $pid: ID!) {
  linkInquiryToPatient(inquiryId: $id, patientId: $pid) {
    id status patient { id }
  }
}
"""


@pytest.fixture
def inquiry(db):
    return Inquiry.objects.create(
        name="Ramesh", phone="9876543210", source="PHONE",
        status=InquiryStatus.NEW, notes="asked about single room",
    )


# --- create ---------------------------------------------------------------

def test_pro_creates_inquiry(pro_client):
    result = pro_client.execute(CREATE, {"data": {
        "name": "  Suresh  ", "source": "WHATSAPP", "phone": "  99999  ",
        "notes": "wants details",
    }})
    assert result.get("errors") is None
    data = result["data"]["createInquiry"]
    assert data["name"] == "Suresh"       # trimmed
    assert data["phone"] == "99999"
    assert data["source"] == "WHATSAPP"
    assert data["status"] == "NEW"
    assert data["createdBy"]["email"] == "pro@nph.test"
    assert Inquiry.objects.count() == 1


def test_create_inquiry_rejects_blank_name(pro_client):
    result = pro_client.execute(CREATE, {"data": {"name": "   ", "source": "PHONE"}})
    assert result["errors"]
    assert Inquiry.objects.count() == 0


# --- list / filter --------------------------------------------------------

def test_inquiries_list_filters_by_status_and_search(pro_client, db):
    Inquiry.objects.create(name="Anita", phone="111", source="PHONE", status=InquiryStatus.NEW)
    Inquiry.objects.create(name="Bala", phone="222", source="WEB", status=InquiryStatus.CLOSED)
    Inquiry.objects.create(name="Chitra", phone="333", source="WEB", status=InquiryStatus.NEW)

    only_new = pro_client.execute(INQUIRIES, {"status": "NEW"})
    names = {r["name"] for r in only_new["data"]["inquiries"]}
    assert names == {"Anita", "Chitra"}

    by_phone = pro_client.execute(INQUIRIES, {"search": "222"})
    assert [r["name"] for r in by_phone["data"]["inquiries"]] == ["Bala"]

    by_name = pro_client.execute(INQUIRIES, {"search": "hit"})
    assert [r["name"] for r in by_name["data"]["inquiries"]] == ["Chitra"]


def test_admin_can_view_inquiries(admin_client, inquiry):
    result = admin_client.execute(INQUIRIES, {})
    assert result.get("errors") is None
    assert len(result["data"]["inquiries"]) == 1


# --- update status --------------------------------------------------------

def test_pro_updates_status(pro_client, inquiry):
    result = pro_client.execute(UPDATE_STATUS, {"id": str(inquiry.id), "status": "FOLLOWED_UP"})
    assert result.get("errors") is None
    assert result["data"]["updateInquiryStatus"]["status"] == "FOLLOWED_UP"
    inquiry.refresh_from_db()
    assert inquiry.status == InquiryStatus.FOLLOWED_UP


def test_cannot_mark_converted_without_patient(pro_client, inquiry):
    result = pro_client.execute(UPDATE_STATUS, {"id": str(inquiry.id), "status": "CONVERTED"})
    assert result["errors"]
    inquiry.refresh_from_db()
    assert inquiry.status == InquiryStatus.NEW


# --- link to patient (conversion) -----------------------------------------

def test_link_inquiry_converts(pro_client, inquiry):
    patient = Patient.objects.create(name="Ramesh", diagnosis="d", admitting_doctor="Dr")
    result = pro_client.execute(LINK, {"id": str(inquiry.id), "pid": str(patient.id)})
    assert result.get("errors") is None
    data = result["data"]["linkInquiryToPatient"]
    assert data["status"] == "CONVERTED"
    assert data["patient"]["id"] == str(patient.id)
    inquiry.refresh_from_db()
    assert inquiry.patient_id == patient.id
    assert inquiry.status == InquiryStatus.CONVERTED


def test_link_inquiry_unknown_patient(pro_client, inquiry):
    result = pro_client.execute(LINK, {"id": str(inquiry.id), "pid": "999999"})
    assert result["errors"]


# --- RBAC -----------------------------------------------------------------

@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client", "anonymous_client"])
def test_inquiries_query_forbidden(request, client_name, inquiry):
    client = request.getfixturevalue(client_name)
    result = client.execute(INQUIRIES, {})
    assert result["errors"]
    assert result["data"] is None or result["data"]["inquiries"] is None


@pytest.mark.parametrize("client_name", ["admin_client", "finance_client", "nurse_client"])
def test_create_inquiry_forbidden_for_non_pro(request, client_name):
    client = request.getfixturevalue(client_name)
    result = client.execute(CREATE, {"data": {"name": "X", "source": "PHONE"}})
    assert result["errors"]
    assert Inquiry.objects.count() == 0


def test_admin_cannot_update_status(admin_client, inquiry):
    result = admin_client.execute(UPDATE_STATUS, {"id": str(inquiry.id), "status": "CLOSED"})
    assert result["errors"]
    inquiry.refresh_from_db()
    assert inquiry.status == InquiryStatus.NEW
