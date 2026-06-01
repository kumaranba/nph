"""Exercises the per-role JWT client fixtures against the schema's RBAC."""
import pytest

ME = "{ me { email role } }"
USERS = "{ users { email role } }"
INVOICES = "{ invoices { id } }"
VITAL_READINGS = "{ vitalReadings { id } }"
ROOMS = "{ rooms { name } }"


def test_me_returns_authenticated_user(admin_client):
    result = admin_client.execute(ME)
    assert result.get("errors") is None
    assert result["data"]["me"] == {"email": "admin@nph.test", "role": "ADMIN"}


def test_admin_can_query_users(admin_client):
    result = admin_client.execute(USERS)
    assert result.get("errors") is None
    assert any(u["email"] == "admin@nph.test" for u in result["data"]["users"])


def test_nurse_cannot_query_users(nurse_client):
    result = nurse_client.execute(USERS)
    # `users` is a non-null field, so a resolver error nullifies all of `data`.
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]


def test_finance_can_query_invoices(finance_client):
    assert finance_client.execute(INVOICES).get("errors") is None


def test_nurse_can_read_vitals_but_not_invoices(nurse_client):
    assert nurse_client.execute(VITAL_READINGS).get("errors") is None
    denied = nurse_client.execute(INVOICES)
    assert "Permission denied" in denied["errors"][0]["message"]


def test_any_authenticated_role_can_read_reference_data(finance_client):
    assert finance_client.execute(ROOMS).get("errors") is None


def test_anonymous_is_rejected(anonymous_client):
    result = anonymous_client.execute(ME)
    assert "Authentication required" in result["errors"][0]["message"]


@pytest.mark.parametrize("role_email", ["admin@nph.test", "finance@nph.test", "nurse@nph.test"])
def test_factory_builds_authed_client(make_role_client, role_email):
    from api.models import UserRole

    role = role_email.split("@")[0].upper()
    client = make_role_client(getattr(UserRole, role), email=role_email)
    result = client.execute(ME)
    assert result["data"]["me"]["email"] == role_email
