import io

from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse, JsonResponse
from strawberry.django.views import GraphQLView

from .auth import get_user_from_request
from .models import UserRole
from .reports import fees_due_pdf


class JWTGraphQLView(GraphQLView):
    """GraphQL view that resolves the JWT bearer token into request.user.

    Stateless: there is no session lookup. If the Authorization header is
    missing or invalid, the user is AnonymousUser and RBAC decorators reject
    protected resolvers.
    """

    def get_context(self, request, response):
        context = super().get_context(request, response)
        context.request.user = get_user_from_request(request) or AnonymousUser()
        return context


def fees_due_pdf_view(request):
    """Download the pending-dues fees report as a PDF. ADMIN + FINANCE only.

    Authentated via the same ``Authorization: Bearer <token>`` header as the
    GraphQL endpoint (no session/cookie).
    """
    user = get_user_from_request(request)
    if user is None:
        return JsonResponse({"error": "Authentication required."}, status=401)
    if user.role not in (UserRole.ADMIN, UserRole.FINANCE):
        return JsonResponse({"error": "Permission denied."}, status=403)

    buffer = io.BytesIO()
    fees_due_pdf(buffer)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="fees-due.pdf"'
    return response
