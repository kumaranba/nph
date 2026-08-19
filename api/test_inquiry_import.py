"""Tests for the OP-list → inquiries bulk import (service + REST endpoint).

The service (`import_op_list`) parses CSV/.xlsx, validates and dedups rows, and
creates OP_IMPORT inquiries. The endpoint (`/inquiries/import`) is PRO-only.
"""
import io
import json

import pytest
from django.test import Client

from api.auth import create_access_token
from api.inquiry_import import ImportFileError, import_op_list
from api.models import Inquiry, InquirySource, InquiryStatus, User, UserRole


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def _xlsx_bytes(rows) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- service: parsing / creation ------------------------------------------

def test_import_csv_creates_inquiries(db):
    data = _csv_bytes(
        "name,phone,notes\n"
        "Ramesh,9876543210,single room\n"
        "Suja,9800000000,\n"
    )
    summary = import_op_list("op.csv", data, None)
    assert summary == {
        "total": 2,
        "created": 2,
        "duplicates": 0,
        "errors": [],
    }
    inq = Inquiry.objects.get(name="Ramesh")
    assert inq.source == InquirySource.OP_IMPORT
    assert inq.status == InquiryStatus.NEW
    assert inq.phone == "9876543210"
    assert inq.notes == "single room"


def test_import_xlsx_creates_inquiries(db):
    data = _xlsx_bytes(
        [["Name", "Mobile", "Remarks"], ["Anitha", "9012345678", "asked fees"]]
    )
    summary = import_op_list("op.xlsx", data, None)
    assert summary["created"] == 1
    inq = Inquiry.objects.get(name="Anitha")
    assert inq.phone == "9012345678"       # 'Mobile' alias → phone
    assert inq.notes == "asked fees"       # 'Remarks' alias → notes


def test_header_aliases_and_column_order(db):
    # 'Patient Name' alias, columns reordered, an unknown column ignored.
    data = _csv_bytes("Extra,Patient Name,Phone\nzzz,Bala,911\n")
    summary = import_op_list("op.csv", data, None)
    assert summary["created"] == 1
    assert Inquiry.objects.get(name="Bala").phone == "911"


# --- service: validation / blanks -----------------------------------------

def test_blank_rows_skipped_not_counted(db):
    data = _csv_bytes("name,phone\nRamesh,911\n,\n   ,  \n")
    summary = import_op_list("op.csv", data, None)
    assert summary["total"] == 1 and summary["created"] == 1


def test_missing_name_is_row_error(db):
    data = _csv_bytes("name,phone\n,911\nSuja,912\n")
    summary = import_op_list("op.csv", data, None)
    assert summary["created"] == 1
    assert summary["errors"] == [{"row": 2, "message": "name is required"}]


def test_missing_name_column_is_file_error(db):
    data = _csv_bytes("phone,notes\n911,hi\n")
    with pytest.raises(ImportFileError):
        import_op_list("op.csv", data, None)


def test_unsupported_extension_is_file_error(db):
    with pytest.raises(ImportFileError):
        import_op_list("op.txt", b"name\nRamesh\n", None)


# --- service: dedup -------------------------------------------------------

def test_dedup_within_file_by_phone(db):
    data = _csv_bytes("name,phone\nRamesh,911\nRam,911\n")
    summary = import_op_list("op.csv", data, None)
    assert summary["created"] == 1 and summary["duplicates"] == 1
    assert Inquiry.objects.count() == 1


def test_dedup_against_existing_op_import(db):
    import_op_list("op.csv", _csv_bytes("name,phone\nRamesh,911\n"), None)
    # Re-uploading the same list is idempotent.
    summary = import_op_list("op.csv", _csv_bytes("name,phone\nRamesh,911\n"), None)
    assert summary["created"] == 0 and summary["duplicates"] == 1
    assert Inquiry.objects.count() == 1


def test_dedup_by_name_when_phone_blank(db):
    data = _csv_bytes("name,phone\nRamesh,\nramesh,\n")
    summary = import_op_list("op.csv", data, None)
    assert summary["created"] == 1 and summary["duplicates"] == 1


def test_manual_inquiry_does_not_block_import(db):
    # A manually-entered inquiry (different source) never blocks an OP import.
    Inquiry.objects.create(name="Ramesh", phone="911", source=InquirySource.PHONE)
    summary = import_op_list("op.csv", _csv_bytes("name,phone\nRamesh,911\n"), None)
    assert summary["created"] == 1


# --- endpoint: RBAC + wiring ----------------------------------------------

def _token(role: UserRole, email: str) -> str:
    user = User.objects.create_user(email=email, password="x", role=role)
    return create_access_token(user)


def _upload(client, token, filename, data):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return client.post(
        "/inquiries/import",
        data={"file": SimpleUploadedFile(filename, data)},
        **({"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}),
    )


def test_endpoint_pro_imports(db):
    token = _token(UserRole.PRO, "pro@nph.test")
    resp = _upload(Client(), token, "op.csv", b"name,phone\nRamesh,911\n")
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert Inquiry.objects.filter(source=InquirySource.OP_IMPORT).count() == 1
    assert Inquiry.objects.get(name="Ramesh").created_by.email == "pro@nph.test"


@pytest.mark.parametrize(
    "role,email",
    [(UserRole.ADMIN, "a@nph.test"), (UserRole.FINANCE, "f@nph.test"),
     (UserRole.NURSE, "n@nph.test")],
)
def test_endpoint_forbidden_for_non_pro(db, role, email):
    token = _token(role, email)
    resp = _upload(Client(), token, "op.csv", b"name\nRamesh\n")
    assert resp.status_code == 403
    assert Inquiry.objects.count() == 0


def test_endpoint_requires_auth(db):
    resp = _upload(Client(), None, "op.csv", b"name\nRamesh\n")
    assert resp.status_code == 401


def test_endpoint_no_file(db):
    token = _token(UserRole.PRO, "pro@nph.test")
    resp = Client().post(
        "/inquiries/import", data={}, HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    assert resp.status_code == 400


def test_endpoint_get_not_allowed(db):
    token = _token(UserRole.PRO, "pro@nph.test")
    resp = Client().get(
        "/inquiries/import", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    assert resp.status_code == 405


def test_endpoint_bad_file_reports_error(db):
    token = _token(UserRole.PRO, "pro@nph.test")
    resp = _upload(Client(), token, "op.csv", b"phone\n911\n")  # no name column
    assert resp.status_code == 400
    assert "name" in resp.json()["error"].lower()
