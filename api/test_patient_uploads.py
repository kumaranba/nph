"""Patient photo / Aadhar-scan uploads (REST, ADMIN) and their GraphQL URLs."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from api.auth import create_access_token
from api.models import Patient, User, UserRole


@pytest.fixture(autouse=True)
def media_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def patient(db):
    return Patient.objects.create(name="Jane", diagnosis="d", admitting_doctor="Dr")


def _png(name="p.png"):
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _client(role):
    user = User.objects.create_user(
        email=f"{role}@up.test", password="secret123", role=role
    )
    c = Client()
    c.defaults["HTTP_AUTHORIZATION"] = f"Bearer {create_access_token(user)}"
    return c


def _post(client, patient_id, path, file):
    return client.post(f"/patients/{patient_id}/{path}", {"file": file})


# --- photo upload -----------------------------------------------------------

def test_photo_upload_requires_auth(patient):
    resp = Client().post(f"/patients/{patient.id}/photo", {"file": _png()})
    assert resp.status_code == 401


def test_photo_upload_forbidden_for_non_admin(patient):
    for role in (UserRole.FINANCE, UserRole.NURSE):
        resp = _post(_client(role), patient.id, "photo", _png())
        assert resp.status_code == 403


def test_admin_uploads_photo(patient):
    resp = _post(_client(UserRole.ADMIN), patient.id, "photo", _png())
    assert resp.status_code == 200
    assert "/media/patient_photos/" in resp.json()["url"]
    patient.refresh_from_db()
    assert patient.photo.name.startswith("patient_photos/")


def test_photo_upload_rejects_non_image(patient):
    bad = SimpleUploadedFile("x.txt", b"hello", content_type="text/plain")
    resp = _post(_client(UserRole.ADMIN), patient.id, "photo", bad)
    assert resp.status_code == 415


def test_photo_upload_missing_file(patient):
    resp = _client(UserRole.ADMIN).post(f"/patients/{patient.id}/photo", {})
    assert resp.status_code == 400


def test_photo_upload_unknown_patient(db):
    resp = _post(_client(UserRole.ADMIN), 999999, "photo", _png())
    assert resp.status_code == 404


# --- aadhar scan upload -----------------------------------------------------

def test_admin_uploads_aadhar_scan_pdf(patient):
    pdf = SimpleUploadedFile("a.pdf", b"%PDF-1.4 ...", content_type="application/pdf")
    resp = _post(_client(UserRole.ADMIN), patient.id, "aadhar-scan", pdf)
    assert resp.status_code == 200
    patient.refresh_from_db()
    assert patient.aadhar_scan.name.startswith("aadhar_scans/")


def test_aadhar_scan_forbidden_for_finance(patient):
    resp = _post(_client(UserRole.FINANCE), patient.id, "aadhar-scan", _png())
    assert resp.status_code == 403


# --- GraphQL exposure -------------------------------------------------------

PHOTO_Q = "query($pk: ID!){ patient(pk: $pk){ photoUrl } }"
SCAN_Q = "query($pk: ID!){ patient(pk: $pk){ aadharScanUrl } }"


def test_photo_url_exposed(admin_client, patient):
    _post(_client(UserRole.ADMIN), patient.id, "photo", _png())
    data = admin_client.execute(PHOTO_Q, {"pk": str(patient.id)})["data"]["patient"]
    assert data["photoUrl"] and "/media/patient_photos/" in data["photoUrl"]


def test_aadhar_scan_url_admin_only(admin_client, finance_client, patient):
    _post(_client(UserRole.ADMIN), patient.id, "aadhar-scan", _png())
    assert admin_client.execute(SCAN_Q, {"pk": str(patient.id)})[
        "data"]["patient"]["aadharScanUrl"]
    denied = finance_client.execute(SCAN_Q, {"pk": str(patient.id)})
    assert denied.get("errors")
    assert "Aadhar" in denied["errors"][0]["message"]
