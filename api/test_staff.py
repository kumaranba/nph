"""Tests for the staff registry — CRUD + RBAC.

RBAC contract: ADMIN manages staff fully; FINANCE, NURSE, PRO have no access.
Staff rows are deactivated (is_active=False), never deleted.
"""
import pytest

from api.models import Staff, StaffDesignation


CREATE = """
mutation($data: CreateStaffInput!) {
  createStaff(data: $data) {
    id staffCode name designation phone isActive joinedOn
  }
}
"""

UPDATE = """
mutation($id: ID!, $data: UpdateStaffInput!) {
  updateStaff(staffId: $id, data: $data) {
    id name designation phone isActive
  }
}
"""

STAFF_LIST = """
query($includeInactive: Boolean, $designation: StaffDesignationEnum, $search: String) {
  staffList(includeInactive: $includeInactive, designation: $designation, search: $search) {
    id staffCode name designation isActive
  }
}
"""


@pytest.fixture
def cook(db):
    return Staff.objects.create(
        name="Lakshmi", designation=StaffDesignation.COOK, phone="900"
    )


# --- create ---------------------------------------------------------------

def test_admin_creates_staff(admin_client):
    result = admin_client.execute(CREATE, {"data": {
        "name": "  Ravi  ", "designation": "SECURITY", "phone": " 911 ",
        "joinedOn": "2026-01-15",
    }})
    assert result.get("errors") is None
    data = result["data"]["createStaff"]
    assert data["name"] == "Ravi"        # trimmed
    assert data["phone"] == "911"
    assert data["designation"] == "SECURITY"
    assert data["isActive"] is True
    assert data["joinedOn"] == "2026-01-15"
    assert data["staffCode"] == "STF-0001"


def test_staff_code_auto_increments(admin_client):
    admin_client.execute(CREATE, {"data": {"name": "A"}})
    admin_client.execute(CREATE, {"data": {"name": "B"}})
    codes = sorted(s.staff_code for s in Staff.objects.all())
    assert codes == ["STF-0001", "STF-0002"]


def test_create_defaults_designation_other(admin_client):
    result = admin_client.execute(CREATE, {"data": {"name": "Nobody"}})
    assert result["data"]["createStaff"]["designation"] == "OTHER"


def test_create_rejects_blank_name(admin_client):
    result = admin_client.execute(CREATE, {"data": {"name": "   "}})
    assert result["errors"]
    assert Staff.objects.count() == 0


# --- list / filter --------------------------------------------------------

def test_list_active_only_by_default(admin_client, cook):
    Staff.objects.create(name="Old Hand", is_active=False)
    result = admin_client.execute(STAFF_LIST, {})
    names = [r["name"] for r in result["data"]["staffList"]]
    assert names == ["Lakshmi"]


def test_list_include_inactive(admin_client, cook):
    Staff.objects.create(name="Old Hand", is_active=False)
    result = admin_client.execute(STAFF_LIST, {"includeInactive": True})
    names = {r["name"] for r in result["data"]["staffList"]}
    assert names == {"Lakshmi", "Old Hand"}


def test_list_filter_by_designation(admin_client, cook):
    Staff.objects.create(name="Meena", designation=StaffDesignation.NURSE)
    result = admin_client.execute(STAFF_LIST, {"designation": "COOK"})
    assert [r["name"] for r in result["data"]["staffList"]] == ["Lakshmi"]


def test_list_search_by_code_and_name(admin_client, cook):
    result = admin_client.execute(STAFF_LIST, {"search": cook.staff_code})
    assert [r["name"] for r in result["data"]["staffList"]] == ["Lakshmi"]
    result = admin_client.execute(STAFF_LIST, {"search": "laksh"})
    assert [r["name"] for r in result["data"]["staffList"]] == ["Lakshmi"]


# --- update / deactivate --------------------------------------------------

def test_admin_updates_staff(admin_client, cook):
    result = admin_client.execute(UPDATE, {
        "id": str(cook.id),
        "data": {"designation": "ATTENDANT", "phone": "999"},
    })
    assert result.get("errors") is None
    cook.refresh_from_db()
    assert cook.designation == StaffDesignation.ATTENDANT
    assert cook.phone == "999"
    assert cook.name == "Lakshmi"       # untouched


def test_deactivate_via_update(admin_client, cook):
    result = admin_client.execute(UPDATE, {
        "id": str(cook.id), "data": {"isActive": False},
    })
    assert result.get("errors") is None
    cook.refresh_from_db()
    assert cook.is_active is False
    # Not deleted — still queryable.
    assert Staff.objects.filter(pk=cook.pk).exists()


def test_update_rejects_blank_name(admin_client, cook):
    result = admin_client.execute(UPDATE, {
        "id": str(cook.id), "data": {"name": "  "},
    })
    assert result["errors"]
    cook.refresh_from_db()
    assert cook.name == "Lakshmi"


def test_update_unknown_staff(admin_client):
    result = admin_client.execute(UPDATE, {
        "id": "999999", "data": {"phone": "1"},
    })
    assert result["errors"]


# --- RBAC -----------------------------------------------------------------

@pytest.mark.parametrize(
    "client_name", ["finance_client", "nurse_client", "pro_client", "anonymous_client"]
)
def test_staff_list_forbidden(request, client_name, cook):
    client = request.getfixturevalue(client_name)
    result = client.execute(STAFF_LIST, {})
    assert result["errors"]
    assert result["data"] is None or result["data"]["staffList"] is None


@pytest.mark.parametrize(
    "client_name", ["finance_client", "nurse_client", "pro_client"]
)
def test_create_staff_forbidden_for_non_admin(request, client_name):
    client = request.getfixturevalue(client_name)
    result = client.execute(CREATE, {"data": {"name": "X"}})
    assert result["errors"]
    assert Staff.objects.count() == 0
