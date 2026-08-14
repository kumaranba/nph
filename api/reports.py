"""PDF report generation (fees-due / pending dues).

Kept dependency-light: uses reportlab (pure Python, no system libraries).
"""
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

# Currency is rendered as "Rs." — the standard PDF fonts have no ₹ glyph.
def _rupee(amount) -> str:
    return f"Rs. {int(amount):,}"


def _fmt_date(d: date) -> str:
    return d.strftime("%d-%b-%Y")


_HEADERS = [
    "S.No", "Patient Name", "DOA", "Current\nFees", "Page#",
    "Total Pending\nDues", "Contact", "Place", "Comments",
]
# Column widths (mm); sum ≈ 190mm usable width on A4 portrait.
_COLW = [11, 44, 22, 20, 13, 26, 26, 24, 24]


def _build_styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "t", parent=styles["Title"], fontSize=15, spaceAfter=2
        ),
        "sub": ParagraphStyle(
            "s", parent=styles["Normal"], fontSize=9,
            textColor=colors.HexColor("#555555"), alignment=TA_CENTER, spaceAfter=8,
        ),
        "cell": ParagraphStyle(
            "c", parent=styles["Normal"], fontSize=8, leading=10
        ),
    }


def _section(story, styles, label, items, as_of):
    story.append(Paragraph("Nila Psychiatric Hospital", styles["title"]))
    total = sum(i.total_pending_dues for i in items)
    story.append(Paragraph(
        f"Fees Due -- Pending Dues ({label})  |  as of {_fmt_date(as_of)}  |  "
        f"{len(items)} patients  |  total {_rupee(total)}",
        styles["sub"],
    ))

    rows = [_HEADERS]
    for n, it in enumerate(items, start=1):
        rows.append([
            str(n),
            Paragraph(it.name, styles["cell"]),
            _fmt_date(it.admission_date),
            _rupee(it.current_fees),
            "",  # Page# — intentionally blank
            _rupee(it.total_pending_dues),
            it.contact,
            Paragraph(it.place, styles["cell"]),
            "",  # Comments — intentionally blank
        ])

    table = Table(rows, colWidths=[w * mm for w in _COLW], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 0), (5, -1), "RIGHT"),
        ("ALIGN", (4, 0), (4, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)


def fees_due_pdf(buffer, as_of: date = None):
    """Render the pending-dues fees report into ``buffer`` (a file-like).

    Male patients and female patients are placed on separate pages, each
    ordered by highest pending dues. Serial numbers restart per list.
    """
    # Imported here to avoid a circular import at module load (schema imports
    # models/billing which are safe; reports is imported by views/schema).
    from .schema import build_pending_dues

    as_of = as_of or date.today()
    items = build_pending_dues(as_of)
    males = [i for i in items if (i.gender or "").upper() == "MALE"]
    females = [i for i in items if (i.gender or "").upper() == "FEMALE"]
    others = [i for i in items if (i.gender or "").upper() not in ("MALE", "FEMALE")]

    styles = _build_styles()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=12 * mm, bottomMargin=12 * mm,
        leftMargin=10 * mm, rightMargin=10 * mm,
        title="Fees Due - Pending Dues",
    )
    story = []
    _section(story, styles, "Male Patients", males, as_of)
    story.append(PageBreak())
    _section(story, styles, "Female Patients", females, as_of)
    if others:
        story.append(PageBreak())
        _section(story, styles, "Unspecified Gender", others, as_of)
    doc.build(story)
    return buffer
