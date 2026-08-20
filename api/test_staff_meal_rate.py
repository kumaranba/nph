"""Tests for Sprint 6 config: Staff.gender + the monthly StaffMealRate.

RBAC: staff gender is edited via the ADMIN-only staff mutations; the staff meal
rate is ADMIN + FINANCE (like the food rate).
"""
from datetime import date
from decimal import Decimal

import pytest

from api.models import Staff, StaffMealRate


# --- Staff.gender ---------------------------------------------------------

CREATE_STAFF = """
mutation($data: CreateStaffInput!) {
  createStaff(data: $data) { id name gender }
}
"""
UPDATE_STAFF = """
mutation($id: ID!, $data: UpdateStaffInput!) {
  updateStaff(staffId: $id, data: $data) { id gender }
}
"""


def test_create_staff_with_gender(admin_client):
    result = admin_client.execute(CREATE_STAFF, {"data": {
        "name": "Lakshmi", "gender": "FEMALE",
    }})
    assert result.get("errors") is None
    assert result["data"]["createStaff"]["gender"] == "FEMALE"


def test_create_staff_gender_optional(admin_client):
    result = admin_client.execute(CREATE_STAFF, {"data": {"name": "Nobody"}})
    assert result.get("errors") is None
    # Gender is optional; unset serialises as an empty string.
    assert result["data"]["createStaff"]["gender"] == ""


def test_update_staff_sets_gender(admin_client, db):
    staff = Staff.objects.create(name="Ravi")
    result = admin_client.execute(UPDATE_STAFF, {
        "id": str(staff.id), "data": {"gender": "MALE"},
    })
    assert result.get("errors") is None
    staff.refresh_from_db()
    assert staff.gender == "MALE"


# --- StaffMealRate --------------------------------------------------------

SET = """
mutation($amount: Decimal!, $from: Date, $note: String) {
  setStaffMealRate(amount: $amount, effectiveFrom: $from, note: $note) {
    id amount effectiveFrom note createdBy { email }
  }
}
"""
RATES = "{ staffMealRates { id amount effectiveFrom } }"
CURRENT = "{ currentStaffMealRate { id amount } }"


def test_rate_on_picks_latest(db):
    StaffMealRate.objects.create(amount=Decimal("1000"), effective_from=date(2026, 1, 1))
    StaffMealRate.objects.create(amount=Decimal("1200"), effective_from=date(2026, 6, 1))
    assert StaffMealRate.rate_on(date(2026, 5, 31)).amount == Decimal("1000")
    assert StaffMealRate.rate_on(date(2026, 6, 1)).amount == Decimal("1200")


def test_finance_sets_rate(finance_client):
    result = finance_client.execute(
        SET, {"amount": "1500", "from": "2026-04-01", "note": " canteen "}
    )
    assert result.get("errors") is None
    data = result["data"]["setStaffMealRate"]
    assert Decimal(data["amount"]) == Decimal("1500")
    assert data["effectiveFrom"] == "2026-04-01"
    assert data["note"] == "canteen"
    assert data["createdBy"]["email"] == "finance@nph.test"


def test_set_rejects_negative(admin_client):
    result = admin_client.execute(SET, {"amount": "-1"})
    assert result["errors"]
    assert StaffMealRate.objects.count() == 0


def test_setting_new_rate_preserves_history(admin_client):
    admin_client.execute(SET, {"amount": "1000", "from": "2026-01-01"})
    admin_client.execute(SET, {"amount": "1200", "from": "2026-06-01"})
    assert StaffMealRate.objects.count() == 2


def test_current_staff_meal_rate(admin_client):
    admin_client.execute(SET, {"amount": "1000", "from": "2020-01-01"})
    result = admin_client.execute(CURRENT)
    assert result["data"]["currentStaffMealRate"]["amount"] == "1000.00"


def test_current_none_when_unset(admin_client):
    result = admin_client.execute(CURRENT)
    assert result["data"]["currentStaffMealRate"] is None


# --- RBAC -----------------------------------------------------------------

@pytest.mark.parametrize("client_name", ["nurse_client", "pro_client", "anonymous_client"])
def test_staff_meal_rates_forbidden(request, client_name):
    client = request.getfixturevalue(client_name)
    result = client.execute(RATES)
    assert result["errors"]
    assert result["data"] is None or result["data"]["staffMealRates"] is None


@pytest.mark.parametrize("client_name", ["nurse_client", "pro_client"])
def test_set_staff_meal_rate_forbidden(request, client_name):
    client = request.getfixturevalue(client_name)
    result = client.execute(SET, {"amount": "1000"})
    assert result["errors"]
    assert StaffMealRate.objects.count() == 0
