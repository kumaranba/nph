from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from api.schema import schema
from api.views import (
    JWTGraphQLView,
    account_statement_pdf_view,
    fees_due_pdf_view,
    food_vendor_list_pdf_view,
    op_list_import_view,
    patient_aadhar_scan_upload_view,
    patient_food_report_pdf_view,
    patient_photo_upload_view,
    receipt_pdf_view,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    # CSRF-exempt: authentication is via the Authorization bearer header,
    # not session cookies, so CSRF protection does not apply.
    path('graphql/', csrf_exempt(JWTGraphQLView.as_view(schema=schema))),
    # Pending-dues fees report (PDF). Bearer-auth, ADMIN + FINANCE.
    path('reports/fees-due.pdf', csrf_exempt(fees_due_pdf_view)),
    # Payment receipt/bill (PDF). Bearer-auth, ADMIN + FINANCE.
    path('reports/receipt/<int:receipt_id>.pdf', csrf_exempt(receipt_pdf_view)),
    # Patient account statement (PDF). Bearer-auth, ADMIN + FINANCE.
    path('reports/statement/<int:patient_id>.pdf',
         csrf_exempt(account_statement_pdf_view)),
    # Food reports (PDF). Bearer-auth, ADMIN + FINANCE.
    path('reports/food-vendor.pdf', csrf_exempt(food_vendor_list_pdf_view)),
    path('reports/patient-food.pdf', csrf_exempt(patient_food_report_pdf_view)),
    # Patient document uploads (multipart). Bearer-auth, ADMIN.
    path('patients/<int:patient_id>/photo',
         csrf_exempt(patient_photo_upload_view)),
    path('patients/<int:patient_id>/aadhar-scan',
         csrf_exempt(patient_aadhar_scan_upload_view)),
    # OP-list bulk import → inquiries (multipart CSV/.xlsx). Bearer-auth, PRO.
    path('inquiries/import', csrf_exempt(op_list_import_view)),
]

# Serve uploaded media from MEDIA_ROOT in development. In production, the web
# server / reverse proxy serves MEDIA_URL directly.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
