"""Tests for the PRM analytics dashboard query."""
from datetime import date

import pytest

from api.models import Inquiry, InquiryStatus, User, UserRole
from api.prm_analytics import build_prm_analytics


def _inq(name, source, status=InquiryStatus.NEW, lost_reason="", owner=None):
    return Inquiry.objects.create(
        name=name, source=source, status=status,
        lost_reason=lost_reason, assigned_to=owner,
    )


@pytest.fixture
def seeded(db):
    pro = User.objects.create_user(email="p1@nph.test", password="x", role=UserRole.PRO)
    _inq("A", "PHONE", InquiryStatus.ADMITTED, owner=pro)
    _inq("B", "PHONE", InquiryStatus.LOST, lost_reason="COST", owner=pro)
    _inq("C", "PHONE", InquiryStatus.NEW, owner=pro)
    _inq("D", "WHATSAPP", InquiryStatus.ADMITTED)
    _inq("E", "WHATSAPP", InquiryStatus.CONTACTED)
    return pro


def test_totals_and_conversion(seeded):
    a = build_prm_analytics()
    assert a.total_leads == 5
    assert a.converted == 2
    assert a.lost == 1
    assert a.open == 2
    assert round(a.conversion_rate, 2) == 0.40


def test_by_source(seeded):
    a = build_prm_analytics()
    by = {s.source: s for s in a.by_source}
    assert by["PHONE"].leads == 3 and by["PHONE"].converted == 1
    assert round(by["WHATSAPP"].conversion_rate, 2) == 0.50   # 1 of 2


def test_by_stage_covers_all_stages(seeded):
    a = build_prm_analytics()
    stages = {s.stage: s.count for s in a.by_stage}
    assert stages["ADMITTED"] == 2 and stages["LOST"] == 1
    # Every pipeline stage is present (even zero ones).
    assert set(stages) == {"NEW", "CONTACTED", "CONSULTED", "ADMITTED", "LOST"}


def test_lost_reasons(seeded):
    a = build_prm_analytics()
    assert [(r.reason, r.count) for r in a.lost_reasons] == [("Cost", 1)]


def test_by_pro(seeded):
    a = build_prm_analytics()
    p = {s.email: s for s in a.by_pro}
    assert p["p1@nph.test"].owned == 3 and p["p1@nph.test"].converted == 1


def test_monthly_has_six_buckets(seeded):
    a = build_prm_analytics(today=date(2026, 8, 26))
    assert len(a.monthly) == 6
    assert a.monthly[-1].month == "2026-08"           # newest last


def test_empty_is_safe(db):
    a = build_prm_analytics()
    assert a.total_leads == 0 and a.conversion_rate == 0.0
    assert a.avg_days_to_convert is None


# --- GraphQL + RBAC -------------------------------------------------------

QUERY = """
query { prmAnalytics { totalLeads converted conversionRate
  bySource { source leads } byStage { stage count } } }
"""


def test_query_works_for_admin(admin_client, seeded):
    result = admin_client.execute(QUERY)
    assert result.get("errors") is None
    assert result["data"]["prmAnalytics"]["totalLeads"] == 5


@pytest.mark.parametrize("client_name", ["finance_client", "nurse_client", "anonymous_client"])
def test_query_forbidden(request, client_name):
    client = request.getfixturevalue(client_name)
    result = client.execute(QUERY)
    assert result["errors"]
    assert result["data"] is None or result["data"]["prmAnalytics"] is None
