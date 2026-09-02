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
    return d.strftime("%d-%m-%Y")


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


# ---------------------------------------------------------------------------
# Payment receipt / bill (one payment event)
# ---------------------------------------------------------------------------

def receipt_pdf(buffer, receipt):
    """Render a Bill/Receipt for a single ``PaymentReceipt`` into ``buffer``."""
    from decimal import Decimal

    patient = receipt.admission.patient
    styles = _build_styles()
    label = ParagraphStyle(
        "lbl", parent=styles["cell"], fontSize=10,
        textColor=colors.HexColor("#555555"),
    )
    value = ParagraphStyle("val", parent=styles["cell"], fontSize=10)

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=16 * mm, bottomMargin=16 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm,
        title=f"Payment Receipt #{receipt.id}",
    )
    story = [
        Paragraph("Nila Psychiatric Hospital", styles["title"]),
        Paragraph(
            f"Payment Receipt #{receipt.id}  |  {_fmt_date(receipt.paid_on)}",
            styles["sub"],
        ),
    ]

    # Patient / meta block.
    meta = [
        ["Patient", Paragraph(patient.name, value)],
        ["Patient ID", Paragraph(patient.patient_id, value)],
        ["Received at", Paragraph(receipt.account.name if receipt.account else "-", value)],
        ["Recorded by", Paragraph(
            receipt.recorded_by.email if receipt.recorded_by else "-", value)],
    ]
    meta_table = Table(meta, colWidths=[35 * mm, 143 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)

    # Amount breakdown.
    allocated = sum((p.amount for p in receipt.payments.all()), Decimal("0"))
    advance = receipt.amount - allocated
    amount_rows = [
        ["Fees payment", _rupee(receipt.fees_amount)],
        ["Additional charges", _rupee(receipt.charges_amount)],
        ["Total received", _rupee(receipt.amount)],
    ]
    amt_table = Table(amount_rows, colWidths=[143 * mm, 35 * mm])
    amt_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, 2), (-1, 2), 0.6, colors.HexColor("#1f2937")),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(Paragraph("<br/>", styles["cell"]))
    story.append(amt_table)

    # What the payment settled (billing periods) + any advance credit.
    lines = [["Billing period", "Applied"]]
    for p in receipt.payments.order_by("invoice__billing_period_start"):
        inv = p.invoice
        period = ("Opening balance" if inv.is_opening_balance
                  else inv.billing_period_start.strftime("%b %Y"))
        lines.append([period, _rupee(p.amount)])
    if advance > 0:
        lines.append(["Advance credit (held)", _rupee(advance)])
    if len(lines) > 1:
        alloc_table = Table(lines, colWidths=[143 * mm, 35 * mm], repeatRows=1)
        alloc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(Paragraph("<br/>Applied to", label))
        story.append(alloc_table)

    doc.build(story)
    return buffer


# ---------------------------------------------------------------------------
# Patient account statement
# ---------------------------------------------------------------------------

def account_statement_pdf(buffer, statement):
    """Render a patient account statement (``AccountStatement``) into buffer."""
    styles = _build_styles()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=14 * mm, bottomMargin=14 * mm,
        leftMargin=14 * mm, rightMargin=14 * mm,
        title=f"Account Statement — {statement.patient_code}",
    )

    # Scope (which admission, or full history) — the primary framing so a shared
    # PDF is unambiguous. A date range, when set, narrows within that scope.
    scope = getattr(statement, "scope_label", "") or "All admissions"
    if statement.date_from or statement.date_to:
        span = (f"{_fmt_date(statement.date_from) if statement.date_from else '…'}"
                f" to {_fmt_date(statement.date_to) if statement.date_to else '…'}")
        scope = f"{scope}  |  {span}"

    story = [
        Paragraph("Nila Psychiatric Hospital", styles["title"]),
        Paragraph(
            f"Account Statement  |  {statement.patient_name} "
            f"({statement.patient_code})  |  {scope}",
            styles["sub"],
        ),
    ]

    rows = [["Date", "Description", "Debit", "Credit", "Balance"]]
    rows.append(["", "Opening balance", "", "", _rupee(statement.opening_balance)])
    for ln in statement.lines:
        rows.append([
            _fmt_date(ln.date),
            Paragraph(ln.description, styles["cell"]),
            _rupee(ln.debit) if ln.debit else "",
            _rupee(ln.credit) if ln.credit else "",
            _rupee(ln.balance),
        ])
    rows.append([
        "", "Closing balance",
        _rupee(statement.total_debits), _rupee(statement.total_credits),
        _rupee(statement.closing_balance),
    ])

    table = Table(
        rows, colWidths=[26 * mm, 74 * mm, 26 * mm, 26 * mm, 30 * mm], repeatRows=1
    )
    last = len(rows) - 1
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (4, -1), "RIGHT"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("LINEABOVE", (0, last), (-1, last), 0.6, colors.HexColor("#1f2937")),
        ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 2), (-1, last - 1),
         [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    note = ("A negative balance is advance credit held on the account."
            if statement.closing_balance < 0 else "")
    if note:
        story.append(Paragraph(f"<br/>{note}", styles["sub"]))

    doc.build(story)
    return buffer


# Month 'YYYY-MM' → 'Month YYYY' for headings.
def _fmt_month(month: str) -> str:
    try:
        y, m = (int(p) for p in month.split("-"))
        return date(y, m, 1).strftime("%B %Y")
    except (ValueError, IndexError):
        return month


def _totals_table_style(last_row):
    """Shared TableStyle for a right-aligned amount table with a bold header and
    a bold totals row at ``last_row``."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("LINEABOVE", (0, last_row), (-1, last_row), 0.6, colors.HexColor("#1f2937")),
        ("FONTNAME", (0, last_row), (-1, last_row), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, last_row - 1),
         [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])


def food_vendor_list_pdf(buffer, data):
    """Render the daily food vendor payment list (``VendorList``) into buffer."""
    styles = _build_styles()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=14 * mm, bottomMargin=14 * mm,
        leftMargin=14 * mm, rightMargin=14 * mm,
        title="Food Vendor Payment List",
    )
    story = [
        Paragraph("Nila Psychiatric Hospital", styles["title"]),
        Paragraph(
            f"Food Vendor Payment List  |  {_fmt_date(data.date_from)} to "
            f"{_fmt_date(data.date_to)}",
            styles["sub"],
        ),
    ]

    rows = [["S.No", "Date", "Patients", "Rate/day", "Amount"]]
    for n, r in enumerate(data.rows, start=1):
        rows.append([
            str(n), _fmt_date(r.day), str(r.patients),
            _rupee(r.rate), _rupee(r.amount),
        ])
    rows.append([
        "", "Total", str(data.total_patient_days), "",
        _rupee(data.total_amount),
    ])

    table = Table(
        rows, colWidths=[16 * mm, 40 * mm, 34 * mm, 40 * mm, 40 * mm],
        repeatRows=1,
    )
    table.setStyle(_totals_table_style(len(rows) - 1))
    story.append(table)
    story.append(Paragraph(
        "<br/>Patient-days count every day from admission through discharge "
        "(both inclusive), priced at the food rate in force each day.",
        styles["sub"],
    ))
    doc.build(story)


def patient_food_report_pdf(buffer, report):
    """Render the patient-wise monthly food report (``PatientFoodReport``)."""
    styles = _build_styles()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=14 * mm, bottomMargin=14 * mm,
        leftMargin=14 * mm, rightMargin=14 * mm,
        title=f"Patient Food Report — {report.month}",
    )
    group_style = ParagraphStyle(
        "grp", parent=styles["title"], fontSize=11, spaceBefore=10, spaceAfter=4,
    )
    story = [
        Paragraph("Nila Psychiatric Hospital", styles["title"]),
        Paragraph(
            f"Patient Food Report  |  {_fmt_month(report.month)}  |  "
            f"rate {_rupee(report.rate)}/patient-day",
            styles["sub"],
        ),
    ]

    for grp in report.groups:
        story.append(Paragraph(
            f"{grp.label} ({len(grp.rows)})", group_style
        ))
        rows = [["S.No", "Patient", "Days", "Rate/day", "Monthly amount"]]
        for n, r in enumerate(grp.rows, start=1):
            rows.append([
                str(n), Paragraph(r.name, styles["cell"]), str(r.days),
                _rupee(r.rate), _rupee(r.amount),
            ])
        rows.append([
            "", "Group total", str(grp.total_days), "", _rupee(grp.total_amount),
        ])
        table = Table(
            rows, colWidths=[16 * mm, 70 * mm, 24 * mm, 40 * mm, 40 * mm],
            repeatRows=1,
        )
        table.setStyle(_totals_table_style(len(rows) - 1))
        story.append(table)

    story.append(Paragraph(
        f"<br/>Grand total: {report.grand_total_days} patient-days  |  "
        f"{_rupee(report.grand_total_amount)}",
        styles["sub"],
    ))
    doc.build(story)


def canteen_report_pdf(buffer, report):
    """Render the monthly canteen meal count (``CanteenReport``) into buffer.

    A daily count table (Male/Female patient + staff, with a Veg/Non-veg patient
    split on Wed & Sun) plus a cost summary. Landscape to fit the columns.
    """
    from reportlab.lib.pagesizes import landscape

    styles = _build_styles()
    show_other = report.has_other
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=12 * mm, bottomMargin=12 * mm,
        leftMargin=12 * mm, rightMargin=12 * mm,
        title=f"Canteen Meal Count — {report.month}",
    )
    story = [
        Paragraph("Nila Psychiatric Hospital", styles["title"]),
        Paragraph(
            f"Canteen Meal Count  |  {_fmt_month(report.month)}",
            styles["sub"],
        ),
    ]

    # Header: patient columns (Male/Female[/Other]) then staff columns.
    head = ["Date", "Day", "Pat-M", "Pat-F"]
    if show_other:
        head.append("Pat-O")
    head += ["Staff-M", "Staff-F"]
    if show_other:
        head.append("Staff-O")
    head.append("Total")

    def pcell(total, nonveg, is_split):
        # "12" normally; "10/2" (veg/non-veg) on split days.
        if is_split and nonveg:
            return f"{total - nonveg}/{nonveg}"
        return str(total)

    rows = [head]
    for d in report.days:
        row = [
            _fmt_date(d.day), d.dow,
            pcell(d.male_patients, d.male_patients_nonveg, d.is_split),
            pcell(d.female_patients, d.female_patients_nonveg, d.is_split),
        ]
        if show_other:
            row.append(pcell(d.other_patients, d.other_patients_nonveg, d.is_split))
        row += [str(d.male_staff), str(d.female_staff)]
        if show_other:
            row.append(str(d.other_staff))
        row.append(str(d.total))
        rows.append(row)

    t = report.totals
    total_row = ["Total", "",
                 str(t.male_patients), str(t.female_patients)]
    if show_other:
        total_row.append(str(t.other_patients))
    total_row += [str(t.male_staff), str(t.female_staff)]
    if show_other:
        total_row.append(str(t.other_staff))
    total_row.append(str(t.total))
    rows.append(total_row)

    ncols = len(head)
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("LINEABOVE", (0, len(rows) - 1), (-1, len(rows) - 1), 0.6,
         colors.HexColor("#1f2937")),
        ("FONTNAME", (0, len(rows) - 1), (-1, len(rows) - 1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, len(rows) - 2),
         [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(table)

    story.append(Paragraph(
        "<br/>Wed &amp; Sun patient cells show Veg/Non-veg. "
        f"Patient meals: {_rupee(report.patient_cost)} "
        f"({t.patient_days} patient-days x daily rate).  "
        f"Staff meals: {_rupee(report.staff_cost)} "
        f"({report.active_staff} active staff x {_rupee(report.staff_monthly_rate)}/mo).  "
        f"Grand total: {_rupee(report.grand_total_cost)}.",
        styles["sub"],
    ))
    doc.build(story)
