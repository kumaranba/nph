"""
Decorator-based RBAC for Strawberry resolvers.

Usage::

    @strawberry.field
    @require_roles(UserRole.ADMIN, UserRole.FINANCE)
    def invoices(self, info: Info) -> list[InvoiceType]:
        return Invoice.objects.all()

The decorated resolver must declare an ``info: Info`` parameter so Strawberry
injects the execution context. The authenticated user is read from
``info.context.request.user`` (populated by ``JWTGraphQLView``).
"""
import functools

from graphql import GraphQLError
from strawberry.types import Info


def _find_info(args, kwargs) -> Info:
    for value in (*args, *kwargs.values()):
        if isinstance(value, Info):
            return value
    raise RuntimeError(
        'RBAC decorator could not find the Strawberry `Info` argument. '
        'Make sure the resolver declares an `info: Info` parameter.'
    )


def _current_user(info: Info):
    return getattr(info.context.request, 'user', None)


def login_required(resolver):
    """Reject the request unless an authenticated user is present."""
    @functools.wraps(resolver)
    def wrapper(*args, **kwargs):
        user = _current_user(_find_info(args, kwargs))
        if user is None or not user.is_authenticated:
            raise GraphQLError('Authentication required.')
        return resolver(*args, **kwargs)
    return wrapper


def require_roles(*roles):
    """Allow only users whose ``role`` is one of ``roles``.

    Accepts either ``UserRole`` enum members or their raw string values.
    """
    allowed = {getattr(r, 'value', r) for r in roles}

    def decorator(resolver):
        @functools.wraps(resolver)
        def wrapper(*args, **kwargs):
            user = _current_user(_find_info(args, kwargs))
            if user is None or not user.is_authenticated:
                raise GraphQLError('Authentication required.')
            if user.role not in allowed:
                raise GraphQLError(
                    'Permission denied: requires role '
                    f'{" or ".join(sorted(allowed))}.'
                )
            return resolver(*args, **kwargs)
        return wrapper
    return decorator
