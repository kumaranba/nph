"""Tests for the OP-consult worklist (R4): consulted_on, setConsulted, the
worklist query, and the import consult-date mapping."""
from datetime import date, timedelta

import pytest

from api.inquiry_import import import_op_list
from api.models import ActivityKind, Inquiry, InquiryStatus, Patient


SET_CONSULTED = """
mutation($id: ID!, $d: Date) {
  setConsulted(inquiryId: $id, consultedOn: $d) { id consultedOn }
}
"""

WORKLIST = """
query { opConsultWorklist { id name consultedOn status } }
"""

CREATE = """
mutation($data: CreateInquiryInput!) {
  createInquiry(data: $data) { id }
}
"""


@pytest.fixture
def inquiry(db):
    return Inquiry.objects.create(name="Ramesh", phone="911", source="OP_CONSULT")


# --- setConsulted ---------------------------------------------------------

def test_pro_marks_consulted_and_logs(pro_client, inquiry):
    result = pro_client.execute(
        SET_CONSULTED, {"id": str(inquiry.id), "d": "2026-08-01"}
    )
    assert result.get("errors") is None
    assert result["data"]["setConsulted"]["consultedOn"] == "2026-08-01"
    inquiry.refresh_from_db()
    assert inquiry.consulted_on == date(2026, 8, 1)
    assert inquiry.activities.filter(type=ActivityKind.SYSTEM).count() == 1


def test_future_consult_date_rejected(pro_client, inquiry):
    future = str(date.today() + timedelta(days=1))
    result = pro_client.execute(SET_CONSULTED, {"id": str(inquiry.id), "d": future})
    assert result["errors"]


def test_create_inquiry_with_consult_date(pro_client):
    result = pro_client.execute(CREATE, {"data": {
        "name": "Suja", "source": "OP_CONSULT", "consultedOn": "2026-07-15",
    }})
    assert result.get("errors") is None
    inq = Inquiry.objects.get(name="Suja")
    assert inq.consulted_on == date(2026, 7, 15)


# --- worklist -------------------------------------------------------------

def test_worklist_only_consulted_open_leads_oldest_first(pro_client, db):
    a = Inquiry.objects.create(name="A", source="OP_CONSULT", consulted_on=date(2026, 3, 5))
    Inquiry.objects.create(name="B", source="OP_CONSULT", consulted_on=date(2026, 3, 1))
    # Consulted but already admitted → excluded.
    p = Patient.objects.create(name="C", diagnosis="d", admitting_doctor="Dr")
    Inquiry.objects.create(name="C", source="OP_CONSULT", consulted_on=date(2026, 2, 1),
                           status=InquiryStatus.ADMITTED, patient=p)
    # Consulted but lost → excluded.
    Inquiry.objects.create(name="D", source="OP_CONSULT", consulted_on=date(2026, 2, 2),
                           status=InquiryStatus.LOST, lost_reason="COST")
    # Never consulted → excluded.
    Inquiry.objects.create(name="E", source="PHONE")

    result = pro_client.execute(WORKLIST, {})
    names = [r["name"] for r in result["data"]["opConsultWorklist"]]
    assert names == ["B", "A"]      # oldest consult first; open leads only


def test_admin_can_view_worklist(admin_client, inquiry):
    inquiry.consulted_on = date(2026, 3, 1)
    inquiry.save()
    result = admin_client.execute(WORKLIST, {})
    assert result.get("errors") is None
    assert len(result["data"]["opConsultWorklist"]) == 1


# --- import consult-date mapping ------------------------------------------

def test_import_maps_consult_date(db):
    data = b"name,phone,consult date\nRamesh,911,15-07-2026\n"
    summary = import_op_list("op.csv", data, None)
    assert summary["created"] == 1
    assert Inquiry.objects.get(name="Ramesh").consulted_on == date(2026, 7, 15)


def test_import_bad_consult_date_is_row_error(db):
    data = b"name,consult date\nRamesh,not-a-date\n"
    summary = import_op_list("op.csv", data, None)
    assert summary["created"] == 0
    assert summary["errors"] and "consult date" in summary["errors"][0]["message"]


# --- RBAC -----------------------------------------------------------------

@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client", "anonymous_client"])
def test_worklist_forbidden(request, client_name, inquiry):
    client = request.getfixturevalue(client_name)
    result = client.execute(WORKLIST, {})
    assert result["errors"]
    assert result["data"] is None or result["data"]["opConsultWorklist"] is None


@pytest.mark.parametrize("client_name", ["admin_client", "finance_client", "nurse_client"])
def test_set_consulted_forbidden_for_non_pro(request, client_name, inquiry):
    client = request.getfixturevalue(client_name)
    result = client.execute(SET_CONSULTED, {"id": str(inquiry.id), "d": "2026-08-01"})
    assert result["errors"]
