"""Tests for the createUser and deactivateUser mutations (Admin only)."""
from api.models import User, UserRole

CREATE_USER = """
mutation CreateUser($email: String!, $password: String!, $role: UserRoleEnum!) {
  createUser(email: $email, password: $password, role: $role) {
    id
    email
    role
    isActive
  }
}
"""

DEACTIVATE_USER = """
mutation DeactivateUser($userId: ID!) {
  deactivateUser(userId: $userId) {
    id
    isActive
  }
}
"""


def test_admin_creates_user(admin_client, db):
    result = admin_client.execute(
        CREATE_USER,
        {"email": "New.Nurse@NPH.test", "password": "secret123", "role": "NURSE"},
    )
    assert result.get("errors") is None
    user = result["data"]["createUser"]
    assert user["email"] == "new.nurse@nph.test"  # normalized to lower-case
    assert user["role"] == "NURSE"
    assert user["isActive"] is True
    # Password is hashed and usable.
    created = User.objects.get(email="new.nurse@nph.test")
    assert created.check_password("secret123")


def test_create_user_rejects_duplicate_email(admin_client, db):
    admin_client.execute(
        CREATE_USER,
        {"email": "dup@nph.test", "password": "secret123", "role": "FINANCE"},
    )
    result = admin_client.execute(
        CREATE_USER,
        {"email": "dup@nph.test", "password": "secret123", "role": "NURSE"},
    )
    assert result["data"] is None
    assert "already exists" in result["errors"][0]["message"]


def test_create_user_rejects_short_password(admin_client, db):
    result = admin_client.execute(
        CREATE_USER,
        {"email": "x@nph.test", "password": "short", "role": "NURSE"},
    )
    assert result["data"] is None
    assert "at least 8" in result["errors"][0]["message"]


def test_nurse_cannot_create_user(nurse_client, db):
    result = nurse_client.execute(
        CREATE_USER,
        {"email": "x@nph.test", "password": "secret123", "role": "NURSE"},
    )
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
    assert not User.objects.filter(email="x@nph.test").exists()


def test_admin_deactivates_user(admin_client, db):
    target = User.objects.create_user(
        email="target@nph.test", password="secret123", role=UserRole.NURSE
    )
    result = admin_client.execute(DEACTIVATE_USER, {"userId": str(target.id)})
    assert result.get("errors") is None
    assert result["data"]["deactivateUser"]["isActive"] is False
    target.refresh_from_db()
    assert target.is_active is False


def test_admin_cannot_deactivate_self(admin_client, db):
    self_id = str(admin_client.user.id)
    result = admin_client.execute(DEACTIVATE_USER, {"userId": self_id})
    assert result["data"] is None
    assert "your own account" in result["errors"][0]["message"]
    admin_client.user.refresh_from_db()
    assert admin_client.user.is_active is True


def test_finance_cannot_deactivate_user(finance_client, db):
    target = User.objects.create_user(
        email="t2@nph.test", password="secret123", role=UserRole.NURSE
    )
    result = finance_client.execute(DEACTIVATE_USER, {"userId": str(target.id)})
    assert result["data"] is None
    assert "Permission denied" in result["errors"][0]["message"]
    target.refresh_from_db()
    assert target.is_active is True
