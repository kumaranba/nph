"""PRM analytics — conversion funnel and productivity over the inquiry pipeline.

Built from ``Inquiry`` rows. A lead is *converted* when its stage is ADMITTED,
*lost* when LOST, and *open* otherwise. An optional date range filters by the
inquiry's creation date; the monthly trend always shows the last six months.
"""
from dataclasses import dataclass, field
from datetime import date

from .models import Inquiry, InquiryStatus, LostReason


@dataclass
class SourceStat:
    source: str
    leads: int
    converted: int
    conversion_rate: float      # 0..1


@dataclass
class StageStat:
    stage: str
    count: int


@dataclass
class LostReasonStat:
    reason: str
    count: int


@dataclass
class MonthStat:
    month: str                  # 'YYYY-MM'
    leads: int


@dataclass
class ProStat:
    email: str
    owned: int
    converted: int


@dataclass
class PrmAnalytics:
    total_leads: int = 0
    converted: int = 0
    lost: int = 0
    open: int = 0
    conversion_rate: float = 0.0
    avg_days_to_convert: float = None
    by_source: list = field(default_factory=list)
    by_stage: list = field(default_factory=list)
    lost_reasons: list = field(default_factory=list)
    monthly: list = field(default_factory=list)
    by_pro: list = field(default_factory=list)


_STAGES = [s.value for s in InquiryStatus]


def _prev_months(today, n):
    """The last ``n`` (year, month) pairs ending with today's month, oldest first."""
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(out))


def build_prm_analytics(date_from=None, date_to=None, today=None) -> PrmAnalytics:
    today = today or date.today()
    qs = Inquiry.objects.all()
    if date_from is not None:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__date__lte=date_to)
    rows = list(
        qs.values("source", "status", "lost_reason", "assigned_to__email",
                  "created_at", "updated_at")
    )

    a = PrmAnalytics()
    a.total_leads = len(rows)

    def is_admitted(r):
        return r["status"] == InquiryStatus.ADMITTED

    a.converted = sum(1 for r in rows if is_admitted(r))
    a.lost = sum(1 for r in rows if r["status"] == InquiryStatus.LOST)
    a.open = a.total_leads - a.converted - a.lost
    a.conversion_rate = (a.converted / a.total_leads) if a.total_leads else 0.0

    # Average days from creation to conversion (approx: updated_at on ADMITTED).
    spans = [
        (r["updated_at"].date() - r["created_at"].date()).days
        for r in rows if is_admitted(r)
    ]
    a.avg_days_to_convert = (sum(spans) / len(spans)) if spans else None

    # By source.
    src = {}
    for r in rows:
        d = src.setdefault(r["source"], [0, 0])
        d[0] += 1
        if is_admitted(r):
            d[1] += 1
    a.by_source = sorted(
        (
            SourceStat(s, n, c, (c / n) if n else 0.0)
            for s, (n, c) in src.items()
        ),
        key=lambda x: x.leads, reverse=True,
    )

    # By stage (fixed pipeline order).
    stage_counts = {s: 0 for s in _STAGES}
    for r in rows:
        stage_counts[r["status"]] = stage_counts.get(r["status"], 0) + 1
    a.by_stage = [StageStat(s, stage_counts[s]) for s in _STAGES]

    # Lost reasons.
    lr = {}
    for r in rows:
        if r["status"] == InquiryStatus.LOST and r["lost_reason"]:
            lr[r["lost_reason"]] = lr.get(r["lost_reason"], 0) + 1
    a.lost_reasons = sorted(
        (LostReasonStat(LostReason(k).label, v) for k, v in lr.items()),
        key=lambda x: x.count, reverse=True,
    )

    # Monthly trend — last 6 months regardless of the filter.
    monthly_qs = Inquiry.objects.values("created_at")
    counts = {}
    for r in monthly_qs:
        d = r["created_at"].date()
        counts[(d.year, d.month)] = counts.get((d.year, d.month), 0) + 1
    a.monthly = [
        MonthStat(f"{y:04d}-{m:02d}", counts.get((y, m), 0))
        for (y, m) in _prev_months(today, 6)
    ]

    # By PRO (assigned owner).
    pro = {}
    for r in rows:
        email = r["assigned_to__email"]
        if not email:
            continue
        d = pro.setdefault(email, [0, 0])
        d[0] += 1
        if is_admitted(r):
            d[1] += 1
    a.by_pro = sorted(
        (ProStat(e, n, c) for e, (n, c) in pro.items()),
        key=lambda x: x.owned, reverse=True,
    )
    return a
