"""Website image uploads (REST, ADMIN) — the SiteImage store behind the
public landing page's gallery/logo."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from api.auth import create_access_token
from api.models import SiteImage, User, UserRole


@pytest.fixture(autouse=True)
def media_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


def _png(name="g.png", size=(4, 3), color="white"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _client(role):
    user = User.objects.create_user(
        email=f"{role}@site.test", password="secret123", role=role
    )
    c = Client()
    c.defaults["HTTP_AUTHORIZATION"] = f"Bearer {create_access_token(user)}"
    return c


def _post(client, **data):
    return client.post("/site/images", data)


# --- auth / RBAC ------------------------------------------------------------

def test_upload_requires_auth(db):
    resp = Client().post("/site/images", {"file": _png()})
    assert resp.status_code == 401
    assert SiteImage.objects.count() == 0


def test_upload_forbidden_for_non_admin(db):
    for role in (UserRole.FINANCE, UserRole.NURSE, UserRole.PRO):
        resp = _post(_client(role), file=_png())
        assert resp.status_code == 403, role
    assert SiteImage.objects.count() == 0


# --- happy path -------------------------------------------------------------

def test_admin_uploads_gallery_image(db):
    resp = _post(
        _client(UserRole.ADMIN),
        file=_png(),
        title_en="Calm rooms",
        title_ta="அமைதியான அறைகள்",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "/media/site_images/" in body["url"]
    img = SiteImage.objects.get(pk=body["id"])
    assert img.section == SiteImage.Section.GALLERY  # default
    assert img.is_active is True
    assert img.title_en == "Calm rooms"
    assert img.title_ta == "அமைதியான அறைகள்"
    assert img.image.name.startswith("site_images/")


def test_section_defaults_and_accepts_valid(db):
    resp = _post(_client(UserRole.ADMIN), file=_png(), section="LOGO")
    assert resp.status_code == 200
    assert SiteImage.objects.get(pk=resp.json()["id"]).section == "LOGO"


# --- validation -------------------------------------------------------------

def test_upload_rejects_unknown_section(db):
    resp = _post(_client(UserRole.ADMIN), file=_png(), section="BOGUS")
    assert resp.status_code == 400
    assert SiteImage.objects.count() == 0


def test_upload_rejects_missing_file(db):
    resp = _post(_client(UserRole.ADMIN))
    assert resp.status_code == 400


def test_upload_rejects_bad_content_type(db):
    bad = SimpleUploadedFile("x.pdf", b"%PDF-1.4", content_type="application/pdf")
    resp = _post(_client(UserRole.ADMIN), file=bad)
    assert resp.status_code == 415
    assert SiteImage.objects.count() == 0


def test_upload_rejects_oversize(db, settings):
    settings.MAX_UPLOAD_BYTES = 10  # smaller than any real image
    resp = _post(_client(UserRole.ADMIN), file=_png())
    assert resp.status_code == 413
    assert SiteImage.objects.count() == 0


# --- downscaling ------------------------------------------------------------

def test_large_image_is_downscaled(db):
    big = _png(name="huge.png", size=(3000, 2000))
    resp = _post(_client(UserRole.ADMIN), file=big)
    assert resp.status_code == 200
    img = SiteImage.objects.get(pk=resp.json()["id"])
    with Image.open(img.image.path) as stored:
        assert max(stored.size) <= 1600


def test_small_image_kept_within_bounds(db):
    resp = _post(_client(UserRole.ADMIN), file=_png(size=(800, 600)))
    assert resp.status_code == 200
    img = SiteImage.objects.get(pk=resp.json()["id"])
    with Image.open(img.image.path) as stored:
        assert stored.size == (800, 600)
