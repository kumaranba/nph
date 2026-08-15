import io
from datetime import datetime

from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse, JsonResponse
from strawberry.django.views import GraphQLView

from .auth import get_user_from_request
from .models import Patient, PaymentReceipt, UserRole
from .reports import account_statement_pdf, fees_due_pdf, receipt_pdf


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


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


def receipt_pdf_view(request, receipt_id):
    """Download a payment receipt/bill as a PDF. ADMIN + FINANCE only.

    Bearer-authenticated like the GraphQL endpoint (no session/cookie).
    """
    user = get_user_from_request(request)
    if user is None:
        return JsonResponse({"error": "Authentication required."}, status=401)
    if user.role not in (UserRole.ADMIN, UserRole.FINANCE):
        return JsonResponse({"error": "Permission denied."}, status=403)

    try:
        receipt = PaymentReceipt.objects.select_related(
            "admission__patient", "account", "recorded_by"
        ).get(pk=receipt_id)
    except PaymentReceipt.DoesNotExist:
        return JsonResponse({"error": "Receipt not found."}, status=404)

    buffer = io.BytesIO()
    receipt_pdf(buffer, receipt)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="receipt-{receipt.id}.pdf"'
    )
    return response


def account_statement_pdf_view(request, patient_id):
    """Download a patient account statement as a PDF. ADMIN + FINANCE only.

    Optional ``from`` / ``to`` (YYYY-MM-DD) query params bound the range.
    Bearer-authenticated like the GraphQL endpoint.
    """
    user = get_user_from_request(request)
    if user is None:
        return JsonResponse({"error": "Authentication required."}, status=401)
    if user.role not in (UserRole.ADMIN, UserRole.FINANCE):
        return JsonResponse({"error": "Permission denied."}, status=403)

    if not Patient.objects.filter(pk=patient_id).exists():
        return JsonResponse({"error": "Patient not found."}, status=404)

    # Imported here to avoid a circular import at module load.
    from .schema import build_account_statement

    statement = build_account_statement(
        patient_id,
        _parse_date(request.GET.get("from")),
        _parse_date(request.GET.get("to")),
    )
    buffer = io.BytesIO()
    account_statement_pdf(buffer, statement)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="statement-{statement.patient_code}.pdf"'
    )
    return response
