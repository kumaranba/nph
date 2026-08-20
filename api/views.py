import io
from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse, JsonResponse
from strawberry.django.views import GraphQLView

from .auth import get_user_from_request
from .canteen import build_canteen_report
from .food_report import build_food_vendor_list, build_patient_food_report
from .inquiry_import import ImportFileError, import_op_list
from .models import Patient, PaymentReceipt, UserRole
from .reports import (
    account_statement_pdf,
    canteen_report_pdf,
    fees_due_pdf,
    food_vendor_list_pdf,
    patient_food_report_pdf,
    receipt_pdf,
)


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


# ---------------------------------------------------------------------------
# Patient document uploads (photo, Aadhar scan)
# ---------------------------------------------------------------------------

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
_SCAN_TYPES = _IMAGE_TYPES | {"application/pdf"}


def _upload_patient_file(request, patient_id, field, allowed_types):
    """Save an uploaded file onto ``patient.<field>``. ADMIN only (uploading
    patient documents matches the ADMIN-only patient edit). Bearer-auth."""
    user = get_user_from_request(request)
    if user is None:
        return JsonResponse({"error": "Authentication required."}, status=401)
    if user.role != UserRole.ADMIN:
        return JsonResponse({"error": "Permission denied."}, status=403)
    try:
        patient = Patient.objects.get(pk=patient_id)
    except Patient.DoesNotExist:
        return JsonResponse({"error": "Patient not found."}, status=404)

    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse({"error": "No file uploaded (field 'file')."}, status=400)
    if upload.size > settings.MAX_UPLOAD_BYTES:
        return JsonResponse({"error": "File is too large."}, status=413)
    if upload.content_type not in allowed_types:
        return JsonResponse(
            {"error": f"Unsupported file type: {upload.content_type}."}, status=415
        )

    getattr(patient, field).save(upload.name, upload, save=True)
    return JsonResponse({"url": getattr(patient, field).url})


def patient_photo_upload_view(request, patient_id):
    """Upload/replace a patient photo (image). ADMIN. multipart field 'file'."""
    return _upload_patient_file(request, patient_id, "photo", _IMAGE_TYPES)


def patient_aadhar_scan_upload_view(request, patient_id):
    """Upload/replace a patient's Aadhar scan (image or PDF). ADMIN."""
    return _upload_patient_file(request, patient_id, "aadhar_scan", _SCAN_TYPES)


def _food_auth(request):
    """Shared auth for food reports: ADMIN + FINANCE, bearer. Returns an error
    JsonResponse or None."""
    user = get_user_from_request(request)
    if user is None:
        return JsonResponse({"error": "Authentication required."}, status=401)
    if user.role not in (UserRole.ADMIN, UserRole.FINANCE):
        return JsonResponse({"error": "Permission denied."}, status=403)
    return None


def food_vendor_list_pdf_view(request):
    """Download the daily food vendor payment list as a PDF. ADMIN + FINANCE.
    Required query params: from, to (YYYY-MM-DD)."""
    denied = _food_auth(request)
    if denied is not None:
        return denied
    date_from = _parse_date(request.GET.get("from"))
    date_to = _parse_date(request.GET.get("to"))
    if date_from is None or date_to is None:
        return JsonResponse(
            {"error": "from and to (YYYY-MM-DD) are required."}, status=400
        )
    if date_to < date_from:
        return JsonResponse(
            {"error": "to must be on or after from."}, status=400
        )
    data = build_food_vendor_list(date_from, date_to)
    buffer = io.BytesIO()
    food_vendor_list_pdf(buffer, data)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="food-vendor-{date_from}-to-{date_to}.pdf"'
    )
    return response


def patient_food_report_pdf_view(request):
    """Download the patient-wise monthly food report as a PDF. ADMIN + FINANCE.
    Optional query param: month (YYYY-MM, defaults to the current month)."""
    denied = _food_auth(request)
    if denied is not None:
        return denied
    month = request.GET.get("month") or None
    try:
        data = build_patient_food_report(month=month)
    except (ValueError, IndexError):
        return JsonResponse(
            {"error": "month must be in YYYY-MM format."}, status=400
        )
    buffer = io.BytesIO()
    patient_food_report_pdf(buffer, data)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="patient-food-{data.month}.pdf"'
    )
    return response


def canteen_report_pdf_view(request):
    """Download the monthly canteen meal count as a PDF. ADMIN + FINANCE.
    Optional query param: month (YYYY-MM, defaults to the current month)."""
    denied = _food_auth(request)
    if denied is not None:
        return denied
    month = request.GET.get("month") or None
    try:
        data = build_canteen_report(month=month)
    except (ValueError, IndexError):
        return JsonResponse(
            {"error": "month must be in YYYY-MM format."}, status=400
        )
    buffer = io.BytesIO()
    canteen_report_pdf(buffer, data)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="canteen-{data.month}.pdf"'
    )
    return response


def op_list_import_view(request):
    """Bulk-import an OP list (CSV or .xlsx) into inquiries. PRO only —
    inquiry management is the PRO's domain. multipart field 'file'. Returns a
    per-row summary: {total, created, duplicates, errors:[{row, message}]}."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)
    user = get_user_from_request(request)
    if user is None:
        return JsonResponse({"error": "Authentication required."}, status=401)
    if user.role != UserRole.PRO:
        return JsonResponse({"error": "Permission denied."}, status=403)

    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse({"error": "No file uploaded (field 'file')."}, status=400)
    if upload.size > settings.MAX_UPLOAD_BYTES:
        return JsonResponse({"error": "File is too large."}, status=413)

    try:
        summary = import_op_list(upload.name, upload.read(), user)
    except ImportFileError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(summary)
