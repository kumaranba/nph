"""Tests for public web-enquiry intake (submitWebEnquiry) and the server-side
phone normalizer.

The submit mutation is deliberately UNAUTHENTICATED — a prospective patient
fills the website form. It is honeypot-guarded, rate-limited, validated, and
creates an unassigned WEB inquiry for PROs to pick up.
"""
import pytest

from api.models import Activity, ActivityKind, Inquiry, InquirySource, InquiryStatus
from api.phones import normalize_phone
from api.schema import WEB_ENQUIRY_RATE


SUBMIT = """
mutation($data: WebEnquiryInput!) {
  submitWebEnquiry(data: $data) { ok message }
}
"""


@pytest.fixture(autouse=True)
def _clear_cache():
    # The rate limiter keys on client IP; the test client always looks like one
    # IP, so isolate the counter between tests.
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


# The submission tests hit the database; the normalizer tests don't need it but
# the shared db mark is harmless.
pytestmark = pytest.mark.django_db


# --- phone normalizer -----------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("9876543210", "+919876543210"),          # bare 10-digit → +91
    ("098765 43210", "+919876543210"),         # trunk 0 + spaces
    ("+91 98765 43210", "+919876543210"),      # already +91
    ("0091 9876543210", "+919876543210"),      # 00 international prefix
    ("+1 415 555 0100", "+14155550100"),       # foreign number kept
    ("", ""),                                    # empty
    ("   ", ""),                                 # blank
    ("12345", "12345"),                          # too short → trimmed original
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


# --- public submission ----------------------------------------------------

def test_public_submit_creates_web_inquiry(anonymous_client):
    result = anonymous_client.execute(SUBMIT, {"data": {
        "name": "  Priya  ",
        "phone": "9876543210",
        "message": "Need admission for my father",
    }})
    assert result.get("errors") is None
    assert result["data"]["submitWebEnquiry"]["ok"] is True

    inq = Inquiry.objects.get()
    assert inq.name == "Priya"                       # trimmed
    assert inq.source == InquirySource.WEB
    assert inq.status == InquiryStatus.NEW
    assert inq.phone == "+919876543210"              # normalized
    assert inq.assigned_to_id is None                # unassigned
    assert inq.created_by_id is None                 # anonymous
    assert "Need admission" in inq.notes
    # A system activity records the submission.
    assert Activity.objects.filter(
        inquiry=inq, type=ActivityKind.SYSTEM
    ).exists()


def test_email_only_is_accepted_and_folded_into_notes(anonymous_client):
    result = anonymous_client.execute(SUBMIT, {"data": {
        "name": "Sam", "email": "sam@example.com",
    }})
    assert result.get("errors") is None
    inq = Inquiry.objects.get()
    assert inq.phone == ""
    assert "Email: sam@example.com" in inq.notes


def test_requires_name(anonymous_client):
    result = anonymous_client.execute(SUBMIT, {"data": {
        "name": "   ", "phone": "9876543210",
    }})
    assert result["errors"]
    assert Inquiry.objects.count() == 0


def test_requires_phone_or_email(anonymous_client):
    result = anonymous_client.execute(SUBMIT, {"data": {"name": "Ghost"}})
    assert result["errors"]
    assert Inquiry.objects.count() == 0


def test_honeypot_silently_accepts_without_creating(anonymous_client):
    result = anonymous_client.execute(SUBMIT, {"data": {
        "name": "Bot", "phone": "9876543210", "company": "SpamCorp",
    }})
    # Looks successful to the bot, but nothing is created.
    assert result.get("errors") is None
    assert result["data"]["submitWebEnquiry"]["ok"] is True
    assert Inquiry.objects.count() == 0


def test_message_is_truncated(anonymous_client):
    long_msg = "x" * 5000
    anonymous_client.execute(SUBMIT, {"data": {
        "name": "Verbose", "phone": "9876543210", "message": long_msg,
    }})
    inq = Inquiry.objects.get()
    # Message capped at 2000; notes also carries the "submitted via website"
    # footer, so just assert the message portion didn't exceed the cap.
    assert inq.notes.count("x") == 2000


def test_rate_limited_after_max(anonymous_client):
    for i in range(WEB_ENQUIRY_RATE):
        r = anonymous_client.execute(SUBMIT, {"data": {
            "name": f"P{i}", "phone": "9876543210",
        }})
        assert r.get("errors") is None
    # The next one from the same IP is throttled.
    blocked = anonymous_client.execute(SUBMIT, {"data": {
        "name": "OneTooMany", "phone": "9876543210",
    }})
    assert blocked["errors"]
    assert "Too many" in blocked["errors"][0]["message"]
    assert Inquiry.objects.count() == WEB_ENQUIRY_RATE
