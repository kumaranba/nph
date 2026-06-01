"""Shared pytest fixtures.

Provides JWT-authenticated GraphQL clients for each role:
``admin_client``, ``finance_client``, ``nurse_client`` — plus an
``anonymous_client`` and a ``make_role_client`` factory for custom cases.

Each client wraps Django's test ``Client`` and POSTs GraphQL operations to
``/graphql/`` with a real ``Authorization: Bearer <access-token>`` header
issued by ``api.auth.create_access_token`` — i.e. the same code path the
running server uses, so RBAC is exercised end to end.
"""
from __future__ import annotations

import json

import pytest
from django.test import Client

from api.auth import create_access_token
from api.models import User, UserRole


class GraphQLClient:
    """Minimal GraphQL-over-HTTP client for tests."""

    endpoint = "/graphql/"

    def __init__(self, token: str | None = None):
        self._client = Client()
        self._token = token
        self.user: User | None = None

    def execute(self, query: str, variables: dict | None = None) -> dict:
        """POST a query/mutation and return the parsed JSON response.

        The response dict has the standard GraphQL shape: ``{"data": ...}``
        and/or ``{"errors": [...]}``.
        """
        extra = {}
        if self._token:
            extra["HTTP_AUTHORIZATION"] = f"Bearer {self._token}"
        response = self._client.post(
            self.endpoint,
            data=json.dumps({"query": query, "variables": variables or {}}),
            content_type="application/json",
            **extra,
        )
        return response.json()


@pytest.fixture
def make_role_client(db):
    """Factory fixture: create a user with ``role`` and return an authed client.

    Usage::

        def test_x(make_role_client):
            client = make_role_client(UserRole.ADMIN, email="x@nph.test")
            client.execute("{ me { email } }")
    """

    def _make(
        role: UserRole,
        *,
        email: str | None = None,
        password: str = "test-pass-123",
    ) -> GraphQLClient:
        email = email or f"{str(role).lower()}@nph.test"
        user = User.objects.create_user(email=email, password=password, role=role)
        client = GraphQLClient(token=create_access_token(user))
        client.user = user
        return client

    return _make


@pytest.fixture
def admin_client(make_role_client) -> GraphQLClient:
    return make_role_client(UserRole.ADMIN, email="admin@nph.test")


@pytest.fixture
def finance_client(make_role_client) -> GraphQLClient:
    return make_role_client(UserRole.FINANCE, email="finance@nph.test")


@pytest.fixture
def nurse_client(make_role_client) -> GraphQLClient:
    return make_role_client(UserRole.NURSE, email="nurse@nph.test")


@pytest.fixture
def anonymous_client() -> GraphQLClient:
    """Unauthenticated GraphQL client (no bearer header)."""
    return GraphQLClient()
