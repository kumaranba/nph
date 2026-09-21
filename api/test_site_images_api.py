"""GraphQL for website images: public gallery/logo reads (unauthenticated) and
ADMIN-only edit / reorder / delete mutations over SiteImage."""
import pytest

from api.models import SiteImage, UserRole


@pytest.fixture
def gallery(db):
    """Three gallery rows (one inactive) + a logo, in a known order."""
    a = SiteImage.objects.create(
        section='GALLERY', image='site_images/a.jpg',
        title_en='Rooms', title_ta='அறைகள்', sort_order=0, is_active=True,
    )
    b = SiteImage.objects.create(
        section='GALLERY', image='site_images/b.jpg',
        title_en='Therapy', title_ta='சிகிச்சை', sort_order=1, is_active=True,
    )
    hidden = SiteImage.objects.create(
        section='GALLERY', image='site_images/c.jpg',
        title_en='Hidden', sort_order=2, is_active=False,
    )
    logo = SiteImage.objects.create(
        section='LOGO', image='site_images/logo.png', is_active=True,
    )
    return {'a': a, 'b': b, 'hidden': hidden, 'logo': logo}


GALLERY_Q = "{ galleryImages { id titleEn titleTa imageUrl sortOrder } }"
LOGO_Q = "{ siteLogo { id imageUrl } }"
SITE_IMAGES_Q = "query($section: String) { siteImages(section: $section) { id section isActive } }"

UPDATE_M = """
mutation($id: ID!, $titleEn: String, $sortOrder: Int, $isActive: Boolean, $section: String) {
  updateSiteImage(imageId: $id, titleEn: $titleEn, sortOrder: $sortOrder,
                  isActive: $isActive, section: $section) {
    id titleEn sortOrder isActive section
  }
}
"""
REORDER_M = """
mutation($ids: [ID!]!) { reorderSiteImages(imageIds: $ids) { id sortOrder } }
"""
DELETE_M = "mutation($id: ID!) { deleteSiteImage(imageId: $id) }"


# --- public reads -----------------------------------------------------------

def test_gallery_images_public_active_only_ordered(anonymous_client, gallery):
    res = anonymous_client.execute(GALLERY_Q)
    assert res.get("errors") is None
    rows = res["data"]["galleryImages"]
    # Only the two active gallery rows, in sort order; the inactive one omitted.
    assert [r["titleEn"] for r in rows] == ["Rooms", "Therapy"]
    assert rows[0]["titleTa"] == "அறைகள்"


def test_site_logo_public_latest_active(anonymous_client, gallery):
    res = anonymous_client.execute(LOGO_Q)
    assert res.get("errors") is None
    assert res["data"]["siteLogo"]["id"] == str(gallery["logo"].id)


def test_site_logo_none_when_absent(anonymous_client, db):
    res = anonymous_client.execute(LOGO_Q)
    assert res.get("errors") is None
    assert res["data"]["siteLogo"] is None


# --- ADMIN management list ---------------------------------------------------

def test_site_images_admin_sees_all_incl_inactive(admin_client, gallery):
    res = admin_client.execute(SITE_IMAGES_Q, {"section": "GALLERY"})
    assert res.get("errors") is None
    rows = res["data"]["siteImages"]
    assert len(rows) == 3  # includes the inactive one
    assert any(r["isActive"] is False for r in rows)


def test_site_images_requires_admin(anonymous_client, nurse_client, gallery):
    for client in (anonymous_client, nurse_client):
        res = client.execute(SITE_IMAGES_Q)
        assert res.get("errors"), "expected auth/permission error"


# --- mutations (RBAC) --------------------------------------------------------

def test_update_site_image_admin(admin_client, gallery):
    res = admin_client.execute(
        UPDATE_M, {"id": str(gallery["a"].id), "titleEn": "Calm rooms", "isActive": False}
    )
    assert res.get("errors") is None
    out = res["data"]["updateSiteImage"]
    assert out["titleEn"] == "Calm rooms" and out["isActive"] is False
    gallery["a"].refresh_from_db()
    assert gallery["a"].title_en == "Calm rooms" and gallery["a"].is_active is False


def test_update_rejects_unknown_section(admin_client, gallery):
    res = admin_client.execute(
        UPDATE_M, {"id": str(gallery["a"].id), "section": "BOGUS"}
    )
    assert res.get("errors")


def test_update_site_image_forbidden_for_non_admin(finance_client, nurse_client, pro_client, gallery):
    for client in (finance_client, nurse_client, pro_client):
        res = client.execute(UPDATE_M, {"id": str(gallery["a"].id), "titleEn": "x"})
        assert res.get("errors")
    gallery["a"].refresh_from_db()
    assert gallery["a"].title_en == "Rooms"  # unchanged


def test_reorder_site_images_admin(admin_client, gallery):
    # Reverse the two active gallery rows.
    res = admin_client.execute(
        REORDER_M, {"ids": [str(gallery["b"].id), str(gallery["a"].id)]}
    )
    assert res.get("errors") is None
    gallery["a"].refresh_from_db(); gallery["b"].refresh_from_db()
    assert gallery["b"].sort_order == 0 and gallery["a"].sort_order == 1


def test_reorder_forbidden_for_non_admin(nurse_client, gallery):
    res = nurse_client.execute(REORDER_M, {"ids": [str(gallery["a"].id)]})
    assert res.get("errors")


def test_delete_site_image_admin(admin_client, gallery):
    res = admin_client.execute(DELETE_M, {"id": str(gallery["hidden"].id)})
    assert res.get("errors") is None
    assert res["data"]["deleteSiteImage"] is True
    assert not SiteImage.objects.filter(pk=gallery["hidden"].id).exists()


def test_delete_forbidden_for_non_admin(finance_client, gallery):
    res = finance_client.execute(DELETE_M, {"id": str(gallery["a"].id)})
    assert res.get("errors")
    assert SiteImage.objects.filter(pk=gallery["a"].id).exists()
