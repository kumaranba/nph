"""Tests for the food vendor rate — effective-dated timeline + RBAC.

RBAC contract: ADMIN + FINANCE may view/set; NURSE and PRO have no access.
Rates are never edited — a change adds a new effective-dated row.
"""
from datetime import date
from decimal import Decimal

import pytest

from api.models import FoodRate


SET = """
mutation($amount: Decimal!, $from: Date, $note: String) {
  setFoodRate(amount: $amount, effectiveFrom: $from, note: $note) {
    id amount effectiveFrom note createdBy { email }
  }
}
"""

RATES = "{ foodRates { id amount effectiveFrom } }"
CURRENT = "{ currentFoodRate { id amount effectiveFrom } }"


# --- rate_on (model) ------------------------------------------------------

def test_rate_on_picks_latest_effective(db):
    FoodRate.objects.create(amount=Decimal("100"), effective_from=date(2026, 1, 1))
    FoodRate.objects.create(amount=Decimal("120"), effective_from=date(2026, 6, 1))
    assert FoodRate.rate_on(date(2026, 5, 31)).amount == Decimal("100")
    assert FoodRate.rate_on(date(2026, 6, 1)).amount == Decimal("120")
    assert FoodRate.rate_on(date(2026, 9, 1)).amount == Decimal("120")


def test_rate_on_none_before_any_rate(db):
    FoodRate.objects.create(amount=Decimal("100"), effective_from=date(2026, 6, 1))
    assert FoodRate.rate_on(date(2026, 1, 1)) is None


# --- set ------------------------------------------------------------------

def test_finance_sets_rate(finance_client):
    result = finance_client.execute(
        SET, {"amount": "125.50", "from": "2026-04-01", "note": " new deal "}
    )
    assert result.get("errors") is None
    data = result["data"]["setFoodRate"]
    assert data["amount"] == "125.50"
    assert data["effectiveFrom"] == "2026-04-01"
    assert data["note"] == "new deal"       # trimmed
    assert data["createdBy"]["email"] == "finance@nph.test"
    assert FoodRate.objects.count() == 1


def test_set_defaults_effective_from_today(admin_client):
    result = admin_client.execute(SET, {"amount": "100"})
    assert result.get("errors") is None
    assert result["data"]["setFoodRate"]["effectiveFrom"] == str(date.today())


def test_set_rejects_negative(admin_client):
    result = admin_client.execute(SET, {"amount": "-1"})
    assert result["errors"]
    assert FoodRate.objects.count() == 0


def test_setting_new_rate_preserves_history(admin_client):
    admin_client.execute(SET, {"amount": "100", "from": "2026-01-01"})
    admin_client.execute(SET, {"amount": "120", "from": "2026-06-01"})
    assert FoodRate.objects.count() == 2       # old row kept


# --- queries --------------------------------------------------------------

def test_food_rates_history_newest_first(admin_client):
    admin_client.execute(SET, {"amount": "100", "from": "2026-01-01"})
    admin_client.execute(SET, {"amount": "120", "from": "2026-06-01"})
    result = admin_client.execute(RATES)
    effs = [r["effectiveFrom"] for r in result["data"]["foodRates"]]
    assert effs == ["2026-06-01", "2026-01-01"]


def test_current_food_rate(admin_client):
    admin_client.execute(SET, {"amount": "100", "from": "2020-01-01"})
    result = admin_client.execute(CURRENT)
    assert result["data"]["currentFoodRate"]["amount"] == "100.00"


def test_current_food_rate_none_when_unset(admin_client):
    result = admin_client.execute(CURRENT)
    assert result["data"]["currentFoodRate"] is None


# --- RBAC -----------------------------------------------------------------

@pytest.mark.parametrize("client_name", ["nurse_client", "pro_client", "anonymous_client"])
def test_food_rates_forbidden(request, client_name):
    client = request.getfixturevalue(client_name)
    result = client.execute(RATES)
    assert result["errors"]
    assert result["data"] is None or result["data"]["foodRates"] is None


@pytest.mark.parametrize("client_name", ["nurse_client", "pro_client"])
def test_set_food_rate_forbidden(request, client_name):
    client = request.getfixturevalue(client_name)
    result = client.execute(SET, {"amount": "100"})
    assert result["errors"]
    assert FoodRate.objects.count() == 0
