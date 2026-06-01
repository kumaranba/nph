"""
Stateless JWT helpers: token creation, decoding, and user resolution.

Tokens are HS256-signed with `settings.JWT_SECRET_KEY`. Two token types are
issued — short-lived `access` tokens (sent on every request via the
`Authorization: Bearer <token>` header) and longer-lived `refresh` tokens
(exchanged for a new pair at the `refreshToken` mutation).
"""
from datetime import datetime, timezone

import jwt
from django.conf import settings

from .models import User

ALGORITHM = settings.JWT_ALGORITHM


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or the wrong type."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _encode(payload: dict, lifetime) -> str:
    now = _now()
    body = {**payload, 'iat': now, 'exp': now + lifetime}
    return jwt.encode(body, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user: User) -> str:
    return _encode(
        {'user_id': user.pk, 'role': user.role, 'type': 'access'},
        settings.JWT_ACCESS_TOKEN_LIFETIME,
    )


def create_refresh_token(user: User) -> str:
    return _encode(
        {'user_id': user.pk, 'type': 'refresh'},
        settings.JWT_REFRESH_TOKEN_LIFETIME,
    )


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise TokenError('Token has expired.')
    except jwt.PyJWTError:
        raise TokenError('Token is invalid.')
    if payload.get('type') != expected_type:
        raise TokenError(f'Expected a {expected_type} token.')
    return payload


def authenticate_user(email: str, password: str) -> User | None:
    """Validate credentials. Returns the User on success, else None."""
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return None
    if user.is_active and user.check_password(password):
        return user
    return None


def get_user_from_request(request) -> User | None:
    """Resolve the authenticated user from the Authorization header, or None."""
    header = request.META.get('HTTP_AUTHORIZATION', '')
    if not header.startswith('Bearer '):
        return None
    token = header[len('Bearer '):].strip()
    try:
        payload = decode_token(token, expected_type='access')
    except TokenError:
        return None
    try:
        return User.objects.get(pk=payload['user_id'], is_active=True)
    except User.DoesNotExist:
        return None
