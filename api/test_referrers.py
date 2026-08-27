"""Tests for PRM referral-source (Referrer) management — CRUD, the leaderboard,
linking to inquiries, and RBAC.

RBAC contract mirrors inquiries: PRO manages referrers fully; ADMIN is
view-only (may read `referrers` / `referrerStats` but not write); FINANCE and
NURSE have no access.
"""
import pytest

from api.models import Inquiry, InquiryStatus, Referrer, ReferrerKind


CREATE = """
mutation($data: CreateReferrerInput!) {
  createReferrer(data: $data) {
    id name kind organization phone email isActive createdBy { email }
  }
}
"""

UPDATE = """
mutation($id: ID!, $data: UpdateReferrerInput!) {
  updateReferrer(referrerId: $id, data: $data) {
    id name kind organization isActive
  }
}
"""

REFERRERS = """
query($inc: Boolean!) {
  referrers(includeInactive: $inc) { id name isActive }
}
"""

STATS = """
query { referrerStats { referrer { id name } leads converted conversionRate } }
"""

CREATE_INQUIRY = """
mutation($data: CreateInquiryInput!) {
  createInquiry(data: $data) { id name referrer { id name } }
}
"""

SET_REF = """
mutation($id: ID!, $ref: ID) {
  setInquiryReferrer(inquiryId: $id, referrerId: $ref) {
    id referrer { id name }
  }
}
"""


@pytest.fixture
def referrer(db):
    return Referrer.objects.create(name="Dr. Rao", kind=ReferrerKind.DOCTOR)


# --- create ---------------------------------------------------------------

def test_pro_creates_referrer(pro_client):
    result = pro_client.execute(CREATE, {"data": {
        "name": "  City Hospital  ",
        "kind": "HOSPITAL",
        "organization": "City Health",
        "phone": "9876543210",
        "email": "ref@city.test",
    }})
    assert result.get("errors") is None
    data = result["data"]["createReferrer"]
    assert data["name"] == "City Hospital"        # trimmed
    assert data["kind"] == "HOSPITAL"
    assert data["isActive"] is True
    assert data["createdBy"]["email"] == "pro@nph.test"
    assert Referrer.objects.count() == 1


def test_create_referrer_defaults_kind_doctor(pro_client):
    result = pro_client.execute(CREATE, {"data": {"name": "Dr. Solo"}})
    assert result.get("errors") is None
    assert result["data"]["createReferrer"]["kind"] == "DOCTOR"


def test_create_referrer_requires_name(pro_client):
    result = pro_client.execute(CREATE, {"data": {"name": "   "}})
    assert result["errors"]
    assert Referrer.objects.count() == 0


# --- update ---------------------------------------------------------------

def test_update_referrer_partial(pro_client, referrer):
    result = pro_client.execute(UPDATE, {
        "id": str(referrer.id),
        "data": {"organization": "New Clinic"},
    })
    assert result.get("errors") is None
    data = result["data"]["updateReferrer"]
    assert data["organization"] == "New Clinic"
    assert data["name"] == "Dr. Rao"              # unchanged
    referrer.refresh_from_db()
    assert referrer.organization == "New Clinic"


def test_deactivate_referrer(pro_client, referrer):
    result = pro_client.execute(UPDATE, {
        "id": str(referrer.id), "data": {"isActive": False},
    })
    assert result.get("errors") is None
    assert result["data"]["updateReferrer"]["isActive"] is False


def test_update_referrer_blank_name_rejected(pro_client, referrer):
    result = pro_client.execute(UPDATE, {
        "id": str(referrer.id), "data": {"name": "  "},
    })
    assert result["errors"]
    referrer.refresh_from_db()
    assert referrer.name == "Dr. Rao"


# --- list -----------------------------------------------------------------

def test_referrers_list_hides_inactive_by_default(pro_client, referrer):
    Referrer.objects.create(name="Old Doc", is_active=False)
    active = pro_client.execute(REFERRERS, {"inc": False})
    names = [r["name"] for r in active["data"]["referrers"]]
    assert names == ["Dr. Rao"]                    # inactive hidden

    all_ = pro_client.execute(REFERRERS, {"inc": True})
    names = [r["name"] for r in all_["data"]["referrers"]]
    assert names == ["Dr. Rao", "Old Doc"]         # ordered by name


# --- leaderboard ----------------------------------------------------------

def test_referrer_stats(pro_client, referrer):
    top = Referrer.objects.create(name="Dr. Top")
    # Dr. Top: 3 leads, 2 converted. Dr. Rao: 1 lead, 0 converted.
    Inquiry.objects.create(name="a", source="REFERRAL", referrer=top,
                           status=InquiryStatus.ADMITTED)
    Inquiry.objects.create(name="b", source="REFERRAL", referrer=top,
                           status=InquiryStatus.ADMITTED)
    Inquiry.objects.create(name="c", source="REFERRAL", referrer=top,
                           status=InquiryStatus.NEW)
    Inquiry.objects.create(name="d", source="REFERRAL", referrer=referrer,
                           status=InquiryStatus.NEW)

    result = pro_client.execute(STATS)
    assert result.get("errors") is None
    rows = result["data"]["referrerStats"]
    # Most leads first.
    assert rows[0]["referrer"]["name"] == "Dr. Top"
    assert rows[0]["leads"] == 3 and rows[0]["converted"] == 2
    assert round(rows[0]["conversionRate"], 2) == 0.67
    assert rows[1]["referrer"]["name"] == "Dr. Rao"
    assert rows[1]["leads"] == 1 and rows[1]["converted"] == 0


def test_referrer_stats_omits_referrers_with_no_leads(pro_client, referrer):
    # referrer has no inquiries → not on the board.
    result = pro_client.execute(STATS)
    assert result["data"]["referrerStats"] == []


# --- linking to inquiries -------------------------------------------------

def test_create_inquiry_with_referrer(pro_client, referrer):
    result = pro_client.execute(CREATE_INQUIRY, {"data": {
        "name": "Lead", "source": "REFERRAL", "referrerId": str(referrer.id),
    }})
    assert result.get("errors") is None
    assert result["data"]["createInquiry"]["referrer"]["name"] == "Dr. Rao"


def test_create_inquiry_bad_referrer_rejected(pro_client):
    result = pro_client.execute(CREATE_INQUIRY, {"data": {
        "name": "Lead", "source": "REFERRAL", "referrerId": "999999",
    }})
    assert result["errors"]
    assert Inquiry.objects.count() == 0


def test_set_and_clear_inquiry_referrer(pro_client, referrer):
    inq = Inquiry.objects.create(name="Lead", source="REFERRAL")
    # attach
    result = pro_client.execute(SET_REF, {
        "id": str(inq.id), "ref": str(referrer.id),
    })
    assert result.get("errors") is None
    assert result["data"]["setInquiryReferrer"]["referrer"]["name"] == "Dr. Rao"
    inq.refresh_from_db()
    assert inq.referrer_id == referrer.id
    # clear
    result = pro_client.execute(SET_REF, {"id": str(inq.id), "ref": None})
    assert result.get("errors") is None
    assert result["data"]["setInquiryReferrer"]["referrer"] is None
    inq.refresh_from_db()
    assert inq.referrer_id is None


# --- RBAC -----------------------------------------------------------------

def test_admin_can_view_referrers(admin_client, referrer):
    result = admin_client.execute(REFERRERS, {"inc": True})
    assert result.get("errors") is None
    assert len(result["data"]["referrers"]) == 1


@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client", "anonymous_client"])
def test_referrers_query_forbidden(request, client_name, referrer):
    client = request.getfixturevalue(client_name)
    result = client.execute(REFERRERS, {"inc": True})
    assert result["errors"]
    assert result["data"] is None or result["data"]["referrers"] is None


@pytest.mark.parametrize("client_name", ["admin_client", "finance_client", "nurse_client"])
def test_create_referrer_forbidden_for_non_pro(request, client_name):
    client = request.getfixturevalue(client_name)
    result = client.execute(CREATE, {"data": {"name": "X"}})
    assert result["errors"]
    assert Referrer.objects.count() == 0


def test_admin_cannot_update_referrer(admin_client, referrer):
    result = admin_client.execute(UPDATE, {
        "id": str(referrer.id), "data": {"name": "Changed"},
    })
    assert result["errors"]
    referrer.refresh_from_db()
    assert referrer.name == "Dr. Rao"
