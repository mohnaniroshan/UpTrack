"""
docs/build_srs.py

Generates the Software Requirements Specification (SRS) for the UpTrack
student project as a polished, submission-ready PDF.

    python docs/build_srs.py   ->   docs/UpTrack_SRS.pdf

Content is grounded in the actual project files (src/*.py, data/*.csv,
data/raw/*.pdf).  Nothing about accuracy numbers, hardware, or unbuilt
modules is fabricated: planned work is clearly labelled "Planned".
"""

from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether, Flowable,
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Drawing, Line, Polygon

HERE = Path(__file__).resolve().parent
OUT  = HERE / "UpTrack_SRS.pdf"

# ── Fonts (Windows Times New Roman + Calibri) ───────────────────────────────
FONTS = Path("C:/Windows/Fonts")

def _register():
    fam = {}
    try:
        pdfmetrics.registerFont(TTFont("TNR",     FONTS / "times.ttf"))
        pdfmetrics.registerFont(TTFont("TNR-Bd",  FONTS / "timesbd.ttf"))
        pdfmetrics.registerFont(TTFont("TNR-It",  FONTS / "timesi.ttf"))
        pdfmetrics.registerFont(TTFont("TNR-BdIt",FONTS / "timesbi.ttf"))
        pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bd",
                                      italic="TNR-It", boldItalic="TNR-BdIt")
        fam["body"] = "TNR"; fam["body_b"] = "TNR-Bd"; fam["body_i"] = "TNR-It"
    except Exception:
        fam["body"] = "Times-Roman"; fam["body_b"] = "Times-Bold"; fam["body_i"] = "Times-Italic"
    try:
        pdfmetrics.registerFont(TTFont("Cal",    FONTS / "calibri.ttf"))
        pdfmetrics.registerFont(TTFont("Cal-Bd", FONTS / "calibrib.ttf"))
        pdfmetrics.registerFontFamily("Cal", normal="Cal", bold="Cal-Bd")
        fam["head"] = "Cal-Bd"; fam["head_r"] = "Cal"
    except Exception:
        fam["head"] = fam["body_b"]; fam["head_r"] = fam["body"]
    return fam

F = _register()
MONO = "Courier"

# ── Palette ─────────────────────────────────────────────────────────────────
NAVY   = HexColor("#1F3A5F")
ACCENT = HexColor("#2E5E8C")
RULE   = HexColor("#B9C6D6")
LIGHT  = HexColor("#E7EEF6")
BOXBG  = HexColor("#EEF3F9")
GREY   = HexColor("#5B6773")
OKG    = HexColor("#2F7D4F")
PLAN   = HexColor("#B4741A")

MARGIN = 2.0 * cm

# ── Styles ──────────────────────────────────────────────────────────────────
ss = getSampleStyleSheet()

def _st(name, **kw):
    return ParagraphStyle(name, **kw)

Body = _st("Body", fontName=F["body"], fontSize=10.5, leading=15,
           alignment=TA_JUSTIFY, spaceAfter=7, textColor=HexColor("#1A1A1A"))
BodyL = _st("BodyL", parent=Body, alignment=TA_LEFT)
Bullet = _st("Bullet", parent=Body, leftIndent=16, bulletIndent=4, spaceAfter=3)
Note  = _st("Note", parent=Body, fontName=F["body_i"], textColor=GREY, fontSize=9.7, leading=13.5)

Title  = _st("Title", fontName=F["head"], fontSize=26, leading=30,
             alignment=TA_CENTER, textColor=NAVY, spaceAfter=6)
Sub    = _st("Sub", fontName=F["head_r"], fontSize=14, leading=18,
             alignment=TA_CENTER, textColor=ACCENT, spaceAfter=4)
Small  = _st("Small", fontName=F["body"], fontSize=10, leading=14, alignment=TA_CENTER, textColor=GREY)

H1 = _st("H1", fontName=F["head"], fontSize=15.5, leading=19, textColor=NAVY,
         spaceBefore=16, spaceAfter=7, keepWithNext=1)
H2 = _st("H2", fontName=F["head"], fontSize=12.5, leading=16, textColor=ACCENT,
         spaceBefore=11, spaceAfter=5, keepWithNext=1)
H3 = _st("H3", fontName=F["head"], fontSize=11, leading=14.5, textColor=HexColor("#33475B"),
         spaceBefore=8, spaceAfter=3, keepWithNext=1)

Cell   = _st("Cell", fontName=F["body"], fontSize=9.2, leading=12)
CellB  = _st("CellB", parent=Cell, fontName=F["body_b"])
CellH  = _st("CellH", fontName=F["head"], fontSize=9.4, leading=12, textColor=white)
CellC  = _st("CellC", parent=Cell, alignment=TA_CENTER)
CellMono = _st("CellMono", parent=Cell, fontName=MONO, fontSize=8.4, leading=11)

TocTitle = _st("TocTitle", fontName=F["head"], fontSize=15.5, textColor=NAVY, spaceAfter=10)

# ── Flowable helpers ────────────────────────────────────────────────────────
story = []

def P(text, style=Body):        story.append(Paragraph(text, style))
def gap(h=6):                   story.append(Spacer(1, h))
def H(text, style):             story.append(Paragraph(text, style))

def bullets(items, style=Bullet):
    for it in items:
        story.append(Paragraph(it, style, bulletText="•"))

def para(text): story.append(Paragraph(text, Body))

def cellp(t, st=Cell):
    return Paragraph(t if t is not None else "", st)

def table(data, widths, header=True, size=9.2, zebra=True, align_center_cols=None,
          header_bg=NAVY, body_font=None):
    align_center_cols = align_center_cols or []
    rows = []
    for r, row in enumerate(data):
        out = []
        for c, val in enumerate(row):
            if isinstance(val, Paragraph):
                out.append(val)
            else:
                if header and r == 0:
                    st = CellH
                else:
                    st = ParagraphStyle("t", parent=Cell, fontSize=size,
                                        fontName=body_font or F["body"])
                    if c in align_center_cols:
                        st = ParagraphStyle("tc", parent=st, alignment=TA_CENTER)
                out.append(Paragraph(str(val), st))
        rows.append(out)
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("LINEBEFORE", (0, 0), (-1, -1), 0.0, RULE),
    ]
    if header:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), header_bg),
                 ("TOPPADDING", (0, 0), (-1, 0), 5),
                 ("BOTTOMPADDING", (0, 0), (-1, 0), 5)]
        if zebra:
            for r in range(2, len(rows), 2):
                cmds.append(("BACKGROUND", (0, r), (-1, r), LIGHT))
    t.setStyle(TableStyle(cmds))
    return t

def down_arrow():
    d = Drawing(140, 16)
    d.add(Line(70, 16, 70, 6, strokeColor=ACCENT, strokeWidth=1.4))
    d.add(Polygon([70, 0, 64, 9, 76, 9], fillColor=ACCENT, strokeColor=ACCENT))
    d.hAlign = "CENTER"
    return d

def flow_box(title, desc, w=13.0 * cm, fill=BOXBG):
    inner = [[Paragraph(f'<b>{title}</b>', _st("fb", parent=Cell, fontSize=10,
                        fontName=F["body_b"], textColor=NAVY, alignment=TA_CENTER)),],
             [Paragraph(desc, _st("fd", parent=Cell, fontSize=8.6, leading=11,
                        textColor=GREY, alignment=TA_CENTER))]]
    t = Table(inner, colWidths=[w])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("BOX", (0, 0), (-1, -1), 0.8, ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    t.hAlign = "CENTER"
    return t

class HRule(Flowable):
    def __init__(self, w, color=RULE, thick=0.8, space=2):
        super().__init__(); self.w = w; self.color = color; self.thick = thick; self.space = space
    def wrap(self, aw, ah): return (self.w, self.space + self.thick)
    def draw(self):
        self.canv.setStrokeColor(self.color); self.canv.setLineWidth(self.thick)
        self.canv.line(0, self.space, self.w, self.space)

CONTENT_W = A4[0] - 2 * MARGIN

def status_tag(kind):
    if kind == "impl":
        return f'<font color="#2F7D4F"><b>Implemented</b></font>'
    if kind == "part":
        return f'<font color="#B4741A"><b>Partial</b></font>'
    return f'<font color="#B4741A"><b>Planned</b></font>'


# ═════════════════════════════════════════════════════════════════════════════
#  TITLE PAGE
# ═════════════════════════════════════════════════════════════════════════════
gap(24)
story.append(HRule(CONTENT_W, NAVY, 1.6))
gap(14)
H("UpTrack", Title)
H("Machine-Learning-Based Infrastructure Project<br/>Delay-Risk Prediction System", Sub)
gap(10)
story.append(HRule(CONTENT_W, NAVY, 1.6))
gap(20)
H("Software Requirements Specification (SRS)", _st("x", parent=Sub, fontSize=16, textColor=NAVY))
gap(6)
H("Software Engineering Laboratory — Project Documentation", Small)
gap(40)

meta_rows = [
    ["Document title", "Software Requirements Specification — UpTrack"],
    ["Version", "1.0"],
    ["Date", "10 September 2026"],
    ["Status", "Draft for academic submission"],
    ["Prepared by", "[Student Name / Roll No.]"],
    ["Course", "Software Engineering Laboratory  [Course Code]"],
    ["Programme / Semester", "[Programme, Semester]"],
    ["Institution", "[Department, Institution]"],
    ["Guide / Faculty", "[Faculty-in-charge]"],
]
story.append(table([[cellp(k, CellB), cellp(v, Cell)] for k, v in meta_rows],
                   [5.0 * cm, CONTENT_W - 5.0 * cm], header=False, zebra=False))
gap(16)
H('Fields in square brackets are placeholders to be completed by the student before submission.', Note)
story.append(PageBreak())


# ═════════════════════════════════════════════════════════════════════════════
#  DOCUMENT CONTROL
# ═════════════════════════════════════════════════════════════════════════════
H("Document Control", H1)

H("Revision History", H2)
story.append(table(
    [["Version", "Date", "Author", "Summary of changes"],
     ["1.0", "10 Sep 2026", "[Student Name]", "First complete SRS covering the UpTrack data pipeline (implemented) and the ML prediction and dashboard modules (planned)."]],
    [2.0 * cm, 2.6 * cm, 3.4 * cm, CONTENT_W - 8.0 * cm]))
gap(8)

H("Approval", H2)
story.append(table(
    [["Role", "Name", "Signature", "Date"],
     ["Author (Student)", "[Name]", "", ""],
     ["Guide / Faculty", "[Name]", "", ""]],
    [4.0 * cm, CONTENT_W - 4.0 * cm - 5.6 * cm, 3.2 * cm, 2.4 * cm]))
gap(10)

H("Compliance with the Required SRS Format", H2)
para("This document follows the four-part structure prescribed for the laboratory, "
     "and adds standard professional SRS material. The table below maps the required "
     "headings to their location in this document.")
story.append(table(
    [["Required heading", "Location in this document"],
     ["1. Introduction — Goal &amp; Objectives of Software", "Section 1 (Goal and Objectives: Section 1.2)"],
     ["2. Information Description — Problem Description", "Section 2.1"],
     ["2. Information Description — Information Flow", "Section 2.2"],
     ["2. Information Description — Hardware Interface", "Section 2.5"],
     ["3. Functional Description — Process Narrative (each function)", "Section 3.2 (F1–F7)"],
     ["4. Design Constraints — Performance Characteristics", "Section 4.1"],
     ["4. Design Constraints — Behavioral Description", "Section 4.2"],
     ["4. Design Constraints — Validation Criteria", "Section 4.3"]],
    [8.6 * cm, CONTENT_W - 8.6 * cm]))
story.append(PageBreak())


# ═════════════════════════════════════════════════════════════════════════════
#  TABLE OF CONTENTS
# ═════════════════════════════════════════════════════════════════════════════
H("Table of Contents", TocTitle)
toc = TableOfContents()
toc.levelStyles = [
    _st("toc0", fontName=F["body_b"], fontSize=11, leading=17, textColor=NAVY,
        leftIndent=0),
    _st("toc1", fontName=F["body"], fontSize=10, leading=15, leftIndent=16),
    _st("toc2", fontName=F["body"], fontSize=9.5, leading=13.5, leftIndent=32, textColor=GREY),
]
story.append(toc)
story.append(PageBreak())


# ═════════════════════════════════════════════════════════════════════════════
#  1. INTRODUCTION
# ═════════════════════════════════════════════════════════════════════════════
H("1. Introduction", H1)

H("1.1 Purpose of this Document", H2)
para("This Software Requirements Specification (SRS) describes the requirements of "
     "<b>UpTrack</b>, a machine-learning-based system that predicts the delay risk of "
     "large public infrastructure projects. UpTrack uses the monthly project-monitoring "
     "data published by the Ministry of Statistics and Programme Implementation (MoSPI), "
     "Government of India (referred to in the project brief as the PAIMANA / MoSPI data), "
     "and presents its predictions through a simple web dashboard.")
para("The document states what the system must do, the information it handles, the "
     "functions it performs, and the constraints under which it operates. It is written "
     "for an academic Software Engineering laboratory submission and is intended to be "
     "detailed enough to guide implementation and to support a viva discussion. Where a "
     "part of the system is already built, this is stated explicitly; where a part is "
     "still planned, it is labelled <i>Planned</i> so that the current state of the "
     "project is never overstated.")

H("1.2 Goal and Objectives of the Software", H2)
H("1.2.1 Goal", H3)
para("<b>Goal.</b> To build a simple, understandable system that reads the Government of "
     "India's monthly infrastructure project-monitoring reports and predicts, for each "
     "ongoing project, whether it is <i>likely to face a delay</i>, then presents that "
     "delay-risk result to a user through an easy-to-read web dashboard.")
H("1.2.2 Objectives", H3)
para("The goal is broken down into the following concrete objectives:")
bullets([
    "<b>O1 — Ingest official data.</b> Read the MoSPI monthly report PDFs (Part-II, "
    "\"List of Tables\") and reliably extract the table of ongoing projects into a clean, "
    "structured dataset.",
    "<b>O2 — Clean and standardise.</b> Convert the raw extracted text into typed fields "
    "(numbers, month/year dates) and handle missing or malformed values without inventing data.",
    "<b>O3 — Track projects over time.</b> Match the same project across successive monthly "
    "reports so that its history (schedule and cost changes) can be observed.",
    "<b>O4 — Prepare features.</b> Derive a small, interpretable set of features (for example "
    "cost escalation, physical/financial progress and schedule slippage) from the project data.",
    "<b>O5 — Predict delay risk.</b> Train a simple classification model that labels each "
    "project as <i>Likely Delayed</i> or <i>Likely On-Time</i>, together with a confidence score.",
    "<b>O6 — Present results.</b> Show the projects and their predicted delay risk on a simple "
    "web dashboard with search and filtering.",
    "<b>O7 — Validate.</b> Verify each stage of the pipeline and evaluate the model with "
    "standard metrics, so the results can be trusted and explained.",
])
para("The current release fully meets Objectives O1 and O2 for the May report and lays the "
     "groundwork for the rest; O3–O6 are planned and O7 is partly met (the data pipeline is "
     "already self-validating). Section 1.7.1 gives the precise status of every component.")

H("1.3 Scope", H2)
para("<b>In scope.</b> UpTrack is an offline, single-user, educational analytics tool. Its scope covers:")
bullets([
    "extraction of the \"Details of Ongoing Projects\" table (Annexure XVIII) from the MoSPI "
    "monthly Part-II report PDFs;",
    "cleaning and structuring of that data into a project dataset;",
    "matching projects across monthly reports and preparing features (planned);",
    "training and applying a simple delay-risk classifier (planned);",
    "a lightweight web dashboard that displays each project and its predicted delay risk (planned).",
])
para("<b>Out of scope.</b> UpTrack does <i>not</i> attempt any of the following: real-time or "
     "streaming data feeds; automatic download of reports from government servers; multi-user "
     "accounts, authentication or role management; financial auditing or official decision-making; "
     "prediction of the exact number of months of delay or the exact cost overrun (the system "
     "predicts a delay-risk category, not a precise figure); and coverage of projects that are not "
     "listed in the MoSPI report used as input. UpTrack is a student project and is not intended "
     "for production or policy use.")

H("1.4 Intended Users and Stakeholders", H2)
story.append(table(
    [["Stakeholder", "Interest in the system"],
     ["Student / Developer", "Builds, runs and demonstrates the system; primary operator of the data pipeline and model."],
     ["Faculty / Evaluator", "Assesses the design, correctness and the student's understanding during the viva."],
     ["Dashboard viewer (end user)", "A non-technical reader who opens the dashboard to see which projects are at risk of delay."],
     ["Data source (MoSPI)", "Publisher of the source reports. Not an interactive user; the system only consumes its public documents."]],
    [4.6 * cm, CONTENT_W - 4.6 * cm]))

H("1.5 Definitions, Acronyms and Abbreviations", H2)
story.append(table(
    [["Term", "Meaning"],
     ["MoSPI", "Ministry of Statistics and Programme Implementation, Government of India — publisher of the monthly project-monitoring reports."],
     ["PAIMANA", "Name used in the project brief for the MoSPI project-monitoring data source."],
     ["Annexure XVIII", "\"Details of Ongoing Projects\" — the specific table in the Part-II report from which project records are extracted."],
     ["Project record", "One row of data describing a single infrastructure project in a monthly report."],
     ["Ongoing project", "A project that has been approved and is under implementation (not yet commissioned)."],
     ["Delay / Time overrun", "A project taking longer than its originally approved commissioning date. Measured in months."],
     ["Cost overrun", "The increase of a project's anticipated cost above its originally approved cost (in Rs. crore)."],
     ["Delay risk", "The system's predicted likelihood that a project is or will be delayed, shown as a category and a score."],
     ["Feature", "A numeric input to the model derived from a project's data (e.g. cost ratio)."],
     ["CSV", "Comma-Separated Values — the tabular file format used for the extracted dataset."],
     ["SRS", "Software Requirements Specification (this document)."]],
    [3.4 * cm, CONTENT_W - 3.4 * cm], size=9.0))

H("1.6 References", H2)
bullets([
    "MoSPI, Government of India — Monthly Flash Report on Central Sector Projects "
    "(Part-II, \"List of Tables\"). Source PDFs used: <font name=\"Courier\">April_Part-II_List_of_tables.pdf</font> "
    "(572 pages) and <font name=\"Courier\">May_Part-2.pdf</font> (571 pages).",
    "Project source code: <font name=\"Courier\">src/extract_may_data.py</font>, "
    "<font name=\"Courier\">src/row_splitter.py</font>, <font name=\"Courier\">src/diagnose_may_pdf.py</font>.",
    "Extracted dataset: <font name=\"Courier\">data/may_projects.csv</font> "
    "(1,817 project records, 13 columns).",
    "Libraries: Python 3.13, pandas 3.0, pdfplumber 0.11. scikit-learn (for the planned model) "
    "and a web framework (for the planned dashboard) are not yet installed.",
], Bullet)

H("1.7 System Overview", H2)
para("UpTrack is organised as a linear pipeline. Official monthly report PDFs are read and the "
     "ongoing-projects table is extracted into a clean dataset. Records for the same project are "
     "matched across months, a small set of features is prepared, and a simple classifier predicts "
     "each project's delay risk. The results are written to a file and shown on a web dashboard. "
     "The pipeline is deliberately simple so that every step can be understood, checked and explained.")
para("The system is built in Python. The implemented data-extraction stage uses <b>pdfplumber</b> "
     "to read the PDF tables and <b>pandas</b> to assemble and validate the dataset. The planned "
     "model stage will use <b>scikit-learn</b>, and the planned dashboard will use a lightweight "
     "Python web framework (for example Streamlit or Flask — to be finalised).")

H("1.7.1 Current Implementation Status", H3)
para("The following table is the single source of truth for what is built today versus what is "
     "planned. It is referenced throughout the document.")
story.append(table(
    [["Component", "Artefact", "Status"],
     ["PDF diagnostics / inspection", "src/diagnose_may_pdf.py", Paragraph(status_tag("impl"), CellC)],
     ["Data extraction (May report)", "src/extract_may_data.py", Paragraph(status_tag("impl"), CellC)],
     ["Row-repair for mangled PDF rows", "src/row_splitter.py", Paragraph(status_tag("impl"), CellC)],
     ["Extracted project dataset", "data/may_projects.csv (1,817 x 13)", Paragraph(status_tag("impl"), CellC)],
     ["Pipeline self-validation report", "in extract_may_data.py", Paragraph(status_tag("impl"), CellC)],
     ["Data extraction (April report)", "planned April extractor", Paragraph(status_tag("plan"), CellC)],
     ["Full preprocessing / type casting", "cleaning module", Paragraph(status_tag("part"), CellC)],
     ["Project matching across months", "matching module", Paragraph(status_tag("plan"), CellC)],
     ["Feature preparation and labelling", "feature module", Paragraph(status_tag("plan"), CellC)],
     ["ML model (training + inference)", "models/", Paragraph(status_tag("plan"), CellC)],
     ["Web dashboard", "app/", Paragraph(status_tag("plan"), CellC)],
     ["Model evaluation / metrics", "evaluation module", Paragraph(status_tag("plan"), CellC)]],
    [6.2 * cm, 6.2 * cm, CONTENT_W - 12.4 * cm], align_center_cols=[2], size=9.0))
gap(3)
H("<b>Implemented</b> = working code exists and runs. "
  "<b>Partial</b> = basic version exists inside another module; a dedicated/complete version is planned. "
  "<b>Planned</b> = designed in this SRS but not yet coded.", Note)
story.append(PageBreak())


# ═════════════════════════════════════════════════════════════════════════════
#  2. INFORMATION DESCRIPTION
# ═════════════════════════════════════════════════════════════════════════════
H("2. Information Description", H1)

H("2.1 Problem Description", H2)
para("Large public infrastructure projects — highways, railway lines, bridges, power and water "
     "projects — are frequently reported as running late and over budget. MoSPI publishes a "
     "monthly report that lists every monitored central-sector project together with its approval "
     "date, original and revised completion dates, costs and expenditure. This information is "
     "published as long PDF documents (over 500 pages each) that are hard to read manually and "
     "difficult to analyse across months.")
para("The core problem UpTrack addresses is: <b>given the information recorded about a project in "
     "the monthly monitoring reports, can we automatically flag whether that project is likely to "
     "be delayed, and present this clearly?</b> Answering this by hand for hundreds of projects is "
     "slow and error-prone. UpTrack automates the reading of the reports, learns the patterns that "
     "accompany delayed projects, and surfaces a simple risk indicator per project.")
para("The learning problem is framed as a <b>binary classification</b>: each project is predicted "
     "to be <i>Likely Delayed</i> or <i>Likely On-Time</i>. In the extracted May dataset the "
     "outcome is naturally derivable and reasonably balanced — of the 1,790 projects that record a "
     "time-overrun value, <b>827 show a delay</b> (time overrun greater than zero months), "
     "<b>912 are on schedule</b> (zero months), and 51 report a negative value (ahead of the "
     "original date). This balance makes the problem well suited to a simple, understandable model "
     "rather than a complex one.")
gap(2)
story.append(KeepTogether([
    Paragraph("<b>Illustrative delay picture in the current dataset (May report)</b>", H3),
    table(
        [["Time-overrun outcome", "Projects", "Interpretation"],
         ["Greater than 0 months", "827", "Delayed (positive class)"],
         ["Exactly 0 months", "912", "On schedule"],
         ["Less than 0 months", "51", "Reported ahead of original date"],
         ["Not recorded", "27", "Missing value in source"],
         ["Total records", "1,817", "All extracted ongoing projects"]],
        [5.4 * cm, 2.6 * cm, CONTENT_W - 8.0 * cm], align_center_cols=[1], size=9.2),
]))

H("2.2 Information Flow", H2)
para("Information moves through UpTrack in one direction, from the official documents to the "
     "dashboard. The required end-to-end flow is:")
gap(2)
H("government project-monitoring data  →  data extraction / cleaning  →  project data  →  "
  "feature preparation  →  ML prediction  →  risk result  →  dashboard",
  _st("flowline", parent=Body, alignment=TA_CENTER, fontName=F["body_i"], textColor=NAVY, fontSize=10.5))
gap(6)
para("The figure below expands each stage, its main input and its main output. Stages are colour-"
     "consistent with the implementation status in Section 1.7.1.")
gap(6)

for i, (t, d, first) in enumerate([
    ("1. Government project-monitoring data",
     "Source: MoSPI monthly Part-II PDFs (April: 572 pp, May: 571 pp). "
     "Table of interest: Annexure XVIII, \"Details of Ongoing Projects\".", True),
    ("2. Data extraction and cleaning  [Implemented for May]",
     "pdfplumber reads the tables page by page; row-repair fixes mangled rows; "
     "values are cleaned (dashes/NA to blank).", False),
    ("3. Project data  [Implemented: data/may_projects.csv]",
     "A tidy table of 1,817 project records x 13 columns, one row per project, "
     "with a unique project_row_id.", False),
    ("4. Feature preparation  [Planned]",
     "Derive interpretable features per project: cost escalation, progress ratio, "
     "schedule slippage, sector, project age.", False),
    ("5. ML prediction  [Planned]",
     "A simple classifier (e.g. logistic regression or decision tree) reads the features "
     "and outputs a delay-risk decision.", False),
    ("6. Risk result  [Planned]",
     "Per project: a label (Likely Delayed / Likely On-Time) and a confidence score, "
     "saved to a results file.", False),
    ("7. Dashboard  [Planned]",
     "A web page lists projects with their risk label and score, and supports "
     "search and filtering by sector.", False),
]):
    story.append(flow_box(t, d))
    if t.startswith("7.") is False:
        story.append(down_arrow())
gap(2)
H("Figure 1 — UpTrack information flow (top to bottom). Bracketed labels show implementation status.", Note)

H("2.3 Data Requirements", H2)
H("2.3.1 Source Data", H3)
para("The only external input is the set of MoSPI monthly Part-II report PDFs, stored under "
     "<font name=\"Courier\">data/raw/</font>. Each report contains Annexure XVIII, "
     "\"Details of Ongoing Projects\", split into sections by sector and ministry (for example "
     "Railways, Road Transport and Highways, Power, Petroleum). Serial numbers restart within each "
     "sector, so the serial number is <i>not</i> globally unique; the extractor therefore assigns "
     "its own unique key. In the May report the ongoing-projects table spans roughly PDF pages "
     "462–575.")

H("2.3.2 Data Dictionary — Extracted Dataset", H3)
para("The extractor produces <font name=\"Courier\">data/may_projects.csv</font> with the 13 "
     "columns below. Costs are in Rs. crore; dates are month/year. Sparse columns are expected "
     "(the source often leaves \"revised\" values blank when a project has not been revised).")
story.append(table(
    [["#", "Column", "Type", "Description", "Missing"],
     ["1", "project_row_id", "text (key)", "Globally unique ID assigned by the extractor (P000001 …).", "0%"],
     ["2", "sl_no", "integer", "Serial number as printed (restarts per sector; not unique).", "0%"],
     ["3", "project_name", "text", "Name of the project as printed in the report.", "0.2%"],
     ["4", "date_of_approval", "month/year", "Date the project was approved.", "0.3%"],
     ["5", "original_date_of_commissioning", "month/year", "Originally planned completion date.", "0.2%"],
     ["6", "revised_date_of_commissioning", "month/year", "Officially revised completion date (if any).", "66%"],
     ["7", "anticipated_date_of_commissioning", "month/year", "Currently anticipated completion date.", "0.2%"],
     ["8", "original_cost_cr", "number", "Originally approved cost (Rs. crore).", "0.2%"],
     ["9", "revised_cost_cr", "number", "Officially revised cost, if any (Rs. crore).", "76%"],
     ["10", "anticipated_cost_cr", "number", "Currently anticipated cost (Rs. crore).", "0.2%"],
     ["11", "cumulative_expenditure_cr", "number", "Money spent so far (Rs. crore).", "0.4%"],
     ["12", "cost_overrun_cr", "number", "Cost overrun as printed (Rs. crore).", "0.5%"],
     ["13", "time_overrun_months", "integer", "Time overrun in months (basis of the delay label).", "1.5%"]],
    [0.8 * cm, 4.5 * cm, 2.0 * cm, CONTENT_W - 0.8 * cm - 4.5 * cm - 2.0 * cm - 1.8 * cm, 1.8 * cm],
    align_center_cols=[0, 4], size=8.7))

H("2.3.3 Derived Data and the Delay Label", H3)
para("Two kinds of data are produced inside the pipeline and are <i>not</i> present in the raw "
     "source:")
bullets([
    "<b>Delay label (target).</b> A project is labelled <i>Delayed</i> when "
    "<font name=\"Courier\">time_overrun_months &gt; 0</font>, and <i>On-Time</i> otherwise. "
    "This label is what the model learns to predict.",
    "<b>Features (inputs).</b> Numeric quantities derived from the columns above, for example the "
    "cost-escalation ratio (anticipated cost / original cost), the progress ratio "
    "(cumulative expenditure / anticipated cost), the schedule gap between anticipated and original "
    "commissioning dates, the project's age since approval, and the sector.",
])
para("<b>Important design note (avoiding target leakage).</b> The columns "
     "<font name=\"Courier\">time_overrun_months</font> and <font name=\"Courier\">cost_overrun_cr</font> "
     "in the <i>same</i> report effectively contain the answer. To keep the prediction meaningful, "
     "the planned design predicts a project's delay status using features drawn from an "
     "<i>earlier</i> monthly report (April) and never feeds the overrun columns of the target month "
     "into the model as inputs. This is why project matching across months (Section 3.2.3) is part "
     "of the design. A simpler single-month baseline may be used first for learning, with this "
     "leakage limitation clearly acknowledged.")

H("2.4 Inputs and Outputs", H2)
story.append(table(
    [["", "Item", "Form", "Produced / consumed by"],
     ["Input", "MoSPI monthly report PDF", "PDF file in data/raw/", "F1 Data collection"],
     ["Intermediate", "Extracted project dataset", "CSV (data/may_projects.csv)", "F1 → F2"],
     ["Intermediate", "Cleaned, typed dataset", "CSV / in-memory table", "F2 Preprocessing"],
     ["Intermediate", "Matched multi-month dataset", "CSV / in-memory table", "F3 Matching (planned)"],
     ["Intermediate", "Feature matrix + labels", "CSV / in-memory table", "F4 Feature prep (planned)"],
     ["Intermediate", "Trained model", "model file in models/", "F5 Training (planned)"],
     ["Output", "Per-project delay-risk result", "CSV + on-screen", "F5 → F6"],
     ["Output", "Dashboard view", "Web page in a browser", "F6 Dashboard (planned)"],
     ["Output", "Validation / evaluation report", "console text / file", "F7 Validation"]],
    [1.8 * cm, 4.6 * cm, 4.6 * cm, CONTENT_W - 11.0 * cm], size=8.9))

H("2.5 Hardware Interface", H2)
para("<b>UpTrack does not require any dedicated, special or custom hardware.</b> It is a pure "
     "software application that runs on an ordinary personal computer. There are no sensors, "
     "microcontrollers, embedded devices, GPUs, scanners or other physical instruments in the "
     "system, and it does not interface with any hardware beyond the standard components of a "
     "normal computer.")
para("The only hardware involved is the user's own computer and its standard peripherals, used in "
     "the usual way:")
bullets([
    "<b>Processing and storage:</b> a standard CPU runs the Python pipeline; the hard disk / SSD "
    "stores the input PDFs, the dataset, the trained model and the results.",
    "<b>Input devices:</b> keyboard and mouse, used to run the pipeline and to operate the "
    "dashboard in a browser.",
    "<b>Display:</b> a normal monitor / screen shows the dashboard and console output.",
    "<b>Network:</b> for the planned dashboard, the browser talks to a local web server over "
    "standard networking (typically <font name=\"Courier\">localhost</font> on the same machine). "
    "No internet connection is required to run the system once the report PDFs are present.",
])
para("A typical student laptop is more than sufficient. Indicative minimum specification: a modern "
     "dual-core CPU, about 4 GB of RAM (8 GB comfortable), and a few hundred megabytes of free disk "
     "space for Python, the PDFs (about 5 MB each) and the generated files. These are guidance "
     "figures for a comfortable experience, not strict hardware requirements.")
gap(2)
story.append(table(
    [["Hardware element", "Role in UpTrack", "Special requirement?"],
     ["CPU", "Runs extraction, model training and inference", "No — any modern CPU"],
     ["RAM", "Holds the ~1,800-row dataset in memory (pandas)", "No — ~4 GB is ample"],
     ["Disk / SSD", "Stores PDFs, CSV dataset, model, results", "No — a few hundred MB free"],
     ["Monitor, keyboard, mouse", "Operate the tool and view the dashboard", "No — standard peripherals"],
     ["Network interface", "Browser ↔ local web server (planned dashboard)", "No — localhost is sufficient"],
     ["GPU / sensors / embedded HW", "Not used", "Not applicable"]],
    [4.4 * cm, CONTENT_W - 4.4 * cm - 4.6 * cm, 4.6 * cm], size=9.0))

H("2.6 Software Interfaces and Dependencies", H2)
para("UpTrack interacts only with software components on the same machine:")
bullets([
    "<b>Operating system / file system:</b> reads the PDF files and writes CSV, model and result "
    "files. Developed on Windows 11 with Python 3.13.",
    "<b>Python libraries (implemented stage):</b> pdfplumber (PDF table reading) and pandas "
    "(data assembly, cleaning and validation).",
    "<b>Python libraries (planned stages):</b> scikit-learn (model), and a web framework such as "
    "Streamlit or Flask (dashboard). These are not yet installed.",
    "<b>Web browser (planned):</b> any modern browser renders the dashboard served locally.",
])
story.append(PageBreak())


# ═════════════════════════════════════════════════════════════════════════════
#  3. FUNCTIONAL DESCRIPTION
# ═════════════════════════════════════════════════════════════════════════════
H("3. Functional Description", H1)

H("3.1 Functional Requirements Summary", H2)
para("The system is composed of seven functions (F1–F7). Each is expanded as a process narrative in "
     "Section 3.2. The table lists the functions, their key requirements and their status.")
story.append(table(
    [["ID", "Function", "Key requirement", "Status"],
     ["F1", "Data collection / import", "Read the report PDF and extract the ongoing-projects table.", Paragraph(status_tag("impl"), CellC)],
     ["F2", "Data preprocessing", "Clean values and cast to numbers / dates; handle missing data.", Paragraph(status_tag("part"), CellC)],
     ["F3", "Project matching", "Match the same project across monthly reports.", Paragraph(status_tag("plan"), CellC)],
     ["F4", "Feature preparation", "Derive interpretable features and the delay label.", Paragraph(status_tag("plan"), CellC)],
     ["F5", "Delay-risk prediction", "Train and apply a simple classifier per project.", Paragraph(status_tag("plan"), CellC)],
     ["F6", "Result display / dashboard", "Show projects and predicted risk in a web page.", Paragraph(status_tag("plan"), CellC)],
     ["F7", "Validation / testing", "Check each stage and evaluate the model.", Paragraph(status_tag("part"), CellC)]],
    [1.0 * cm, 3.4 * cm, CONTENT_W - 1.0 * cm - 3.4 * cm - 2.6 * cm, 2.6 * cm],
    align_center_cols=[3], size=9.0))

# Reusable narrative renderer
def narrative(idtag, title, status_kind, purpose, inputs, steps, outputs, errors, extra=None):
    H(f"{idtag} {title}", H3)
    P(f"<b>Status:</b> {status_tag(status_kind)}", Note)
    P(f"<b>Purpose.</b> {purpose}")
    P(f"<b>Inputs.</b> {inputs}")
    P("<b>Processing steps.</b>")
    for n, s in enumerate(steps, 1):
        story.append(Paragraph(f"{n}. {s}", _st("num", parent=Body, leftIndent=16, spaceAfter=2)))
    P(f"<b>Outputs.</b> {outputs}")
    P(f"<b>Error handling.</b> {errors}")
    if extra:
        P(extra)
    gap(2)

H("3.2 Process Narrative for Each Function", H2)

narrative(
    "3.2.1  F1 —", "Data Collection / Import", "impl",
    "Turn an official monthly report PDF into a clean, structured table of ongoing projects.",
    "A MoSPI Part-II PDF in <font name=\"Courier\">data/raw/</font> (currently the May report).",
    ["Open the PDF and select the page range that contains Annexure XVIII "
     "(\"Details of Ongoing Projects\"), excluding the tail of the previous annexure so serial "
     "numbers do not collide.",
     "For each page, extract table rows with pdfplumber using a line-based table strategy, falling "
     "back to a text strategy and then to a word-position strategy if needed.",
     "Repair the small number of rows that the PDF extractor mangles, using three known patterns: "
     "a serial number glued to the project name; two projects merged into one row; and an orphan "
     "data row whose serial and name are missing from the PDF text layer.",
     "Assemble physical rows into one logical record per project, tracking the current sector "
     "section and skipping headers, page numbers and subtotal / grand-total rows.",
     "Assign a globally unique <font name=\"Courier\">project_row_id</font> and write the 13-column "
     "dataset to <font name=\"Courier\">data/may_projects.csv</font>."],
    "A CSV file of 1,817 project records with 13 columns, plus a console validation report.",
    "If the PDF is missing the program stops with a clear message. Rows that cannot be parsed are "
    "recorded in a skip log with the reason; totals and headers are deliberately skipped; genuinely "
    "absent project names are left blank rather than being invented.",
    "<b>Implemented in</b> <font name=\"Courier\">src/extract_may_data.py</font> and "
    "<font name=\"Courier\">src/row_splitter.py</font>. <b>Planned extension:</b> a matching extractor "
    "for the April report, reusing the same logic.")

narrative(
    "3.2.2  F2 —", "Data Preprocessing / Cleaning", "part",
    "Convert the extracted text fields into clean, typed values ready for analysis.",
    "The extracted dataset from F1.",
    ["Strip stray characters and treat dashes and \"NA\"/\"NIL\" as missing (already done during "
     "extraction).",
     "Cast cost and expenditure columns to numbers (removing thousands separators) and time overrun "
     "to an integer.",
     "Parse the month/year date columns into a consistent date representation.",
     "Record, but do not fabricate, missing values; keep an explicit missing-value profile per column.",
     "Optionally drop or flag records that are unusable for modelling (for example, missing the "
     "fields needed to compute a feature)."],
    "A cleaned, typed dataset (in memory and/or a cleaned CSV) with a documented missing-value profile.",
    "Values that cannot be parsed are set to missing and counted, never guessed. The step reports "
    "how many values in each column were converted, blank or dropped.",
    "<b>Partial:</b> basic cleaning (dash / NA handling, thousands-separator removal at read time) "
    "already happens inside F1; a dedicated, complete preprocessing step with full date parsing and "
    "type casting is <i>planned</i> as a separate, testable module.")

narrative(
    "3.2.3  F3 —", "Project Matching Across Monthly Reports", "plan",
    "Recognise the same project in two different monthly reports so that its history can be tracked "
    "and, crucially, so that earlier-month features can be paired with a later-month outcome.",
    "Two cleaned datasets from two months (e.g. April and May).",
    ["Normalise project names (upper-case, collapse spaces, remove punctuation) to compare them fairly.",
     "Match records primarily on the normalised project name within the same sector section.",
     "Use supporting fields (approval date, original cost) to confirm a match and to break ties.",
     "Classify each project as matched (present in both months), new, or dropped, and record the counts.",
     "Produce a combined table that links each project's April record to its May record."],
    "A matched, multi-month dataset that pairs each project across the two reports, with match "
    "statistics.",
    "Ambiguous or low-confidence matches are left unmatched and reported rather than forced. Because "
    "names in the source can vary slightly between months, the matching rate is reported as a quality "
    "measure and manual spot-checks are expected.",
    "<b>Planned.</b> This function enables the leakage-free prediction design described in Section 2.3.3.")

narrative(
    "3.2.4  F4 —", "Feature Preparation", "plan",
    "Turn each project's raw fields into a small, interpretable set of numeric features and attach "
    "the delay label.",
    "The cleaned (and, for the leakage-free design, matched) dataset.",
    ["Compute the delay label from the target month: Delayed if time overrun &gt; 0, else On-Time.",
     "Derive features from the earlier-month fields: cost-escalation ratio (anticipated / original "
     "cost), progress ratio (expenditure / anticipated cost), schedule gap in months (anticipated "
     "minus original commissioning date), project age since approval, and the sector.",
     "Encode the sector as a categorical feature (e.g. one-hot) and scale numeric features if the "
     "chosen model needs it.",
     "Handle any remaining missing feature values with a simple, documented rule (e.g. median or a "
     "\"missing\" flag).",
     "Split the data into training and test sets (e.g. 80/20)."],
    "A feature matrix with one row per project, a matching label column, and a train/test split.",
    "Features that cannot be computed (missing inputs) are imputed by a stated rule or the record is "
    "excluded; the count of excluded records is reported. The step asserts that no target-derived "
    "column is used as an input feature.",
    "<b>Planned.</b> The feature set is intentionally small and explainable, suitable for a student "
    "project and easy to defend in a viva.")

narrative(
    "3.2.5  F5 —", "Delay-Risk Prediction", "plan",
    "Learn the pattern of delayed versus on-time projects and predict a delay-risk category for each "
    "project.",
    "The feature matrix and labels from F4.",
    ["Train a simple, interpretable classifier on the training set — for example logistic regression "
     "or a decision tree / small random forest from scikit-learn.",
     "Apply the trained model to the test set and to any project needing a prediction.",
     "For each project output a category (Likely Delayed / Likely On-Time) and a confidence score "
     "(probability) between 0 and 1.",
     "Save the trained model to <font name=\"Courier\">models/</font> and the predictions to a results file."],
    "A trained model file and a per-project results table (id, name, predicted label, score).",
    "If the model cannot produce a probability for a record, it falls back to the majority-class "
    "prediction and flags the record. The methodology is deliberately kept simple; no deep-learning "
    "or ensemble complexity is required.",
    "<b>Planned.</b> No accuracy figure is claimed in this document because the model has not yet "
    "been trained; target metrics are given as goals in Section 4.3 and marked TBD until measured.")

narrative(
    "3.2.6  F6 —", "Result Display / Dashboard", "plan",
    "Present the projects and their predicted delay risk to a user through a simple web page.",
    "The per-project results file from F5.",
    ["Load the results into a lightweight web application.",
     "Show a table of projects with name, sector, key figures and the predicted risk label and score.",
     "Colour or badge each row by risk (e.g. red for Likely Delayed, green for Likely On-Time).",
     "Provide search by project name and filtering by sector and by risk category.",
     "Show a small summary (counts of at-risk vs on-time projects, and simple charts)."],
    "An interactive dashboard page viewable in a browser.",
    "If the results file is missing or empty, the dashboard shows a clear, friendly message instead "
    "of crashing. Invalid filter input returns an empty result set with an explanatory note.",
    "<b>Planned.</b> The dashboard is intentionally simple (a single main page). The web framework "
    "(Streamlit or Flask) will be finalised during implementation.")

narrative(
    "3.2.7  F7 —", "Validation / Testing", "part",
    "Confirm that each stage behaves correctly and that the model's quality is measured and reported.",
    "Outputs of every stage.",
    ["Validate extraction: correct column count (13), unique ids, no total/subtotal rows leaked, "
     "expected missing-value profile, and structured (not fallback) extraction on data pages.",
     "Validate preprocessing: numeric fields are numeric, dates parse, and counts of converted / "
     "missing values are reported.",
     "Validate matching: report matched / new / dropped counts and spot-check a sample.",
     "Evaluate the model: report accuracy, precision, recall, F1-score and a confusion matrix on the "
     "test set.",
     "Validate the dashboard: every project shows a label and score, filters work, and empty/error "
     "states are handled."],
    "A validation report (console and/or file) and, for the model, an evaluation summary.",
    "Any failed check is reported clearly; the extraction stage already exits with a non-zero status "
    "and a warning when a check fails, so problems are visible rather than silent.",
    "<b>Partial:</b> the extraction stage already produces a detailed self-validation report "
    "(Section 4.3); model evaluation and dashboard checks are <i>planned</i>.")

H("3.3 ML / Prediction Requirements", H2)
para("These requirements keep the machine-learning part simple, honest and explainable.")
bullets([
    "<b>ML-R1.</b> The task is binary classification: predict Delayed vs On-Time for each project.",
    "<b>ML-R2.</b> The delay label is defined once and clearly: Delayed when time overrun &gt; 0 months.",
    "<b>ML-R3.</b> Only a small, interpretable feature set is used (Section 3.2.4); no opaque or "
    "hand-tuned complex features.",
    "<b>ML-R4.</b> The model is a simple, well-understood classifier (logistic regression or a "
    "decision-tree / small random forest). Deep learning is explicitly out of scope.",
    "<b>ML-R5.</b> Target leakage is avoided: overrun columns of the predicted month are never used "
    "as inputs; the intended design predicts from an earlier month's features.",
    "<b>ML-R6.</b> The model is evaluated with a train/test split and standard metrics (accuracy, "
    "precision, recall, F1, confusion matrix).",
    "<b>ML-R7.</b> Every prediction includes a confidence score in the range 0 to 1.",
    "<b>ML-R8.</b> No accuracy figure is asserted until it has actually been measured; targets are "
    "goals only (see Section 4.3).",
])

H("3.4 Dashboard Requirements", H2)
bullets([
    "<b>DB-R1.</b> Display all predicted projects in a searchable, sortable table.",
    "<b>DB-R2.</b> Show, per project: name, sector, original and anticipated cost, key dates, "
    "predicted risk label and confidence score.",
    "<b>DB-R3.</b> Visually distinguish at-risk projects (e.g. colour badge).",
    "<b>DB-R4.</b> Allow filtering by sector and by risk category, and search by project name.",
    "<b>DB-R5.</b> Show a summary panel with counts and a simple chart of at-risk vs on-time projects.",
    "<b>DB-R6.</b> Run locally in a browser without requiring an internet connection.",
    "<b>DB-R7.</b> Handle missing/empty results and bad input gracefully with clear messages.",
])
story.append(PageBreak())


# ═════════════════════════════════════════════════════════════════════════════
#  4. DESIGN CONSTRAINTS
# ═════════════════════════════════════════════════════════════════════════════
H("4. Design Constraints", H1)

H("4.1 Performance Characteristics", H2)
para("UpTrack is an offline, batch-oriented tool for a single user; it does not need real-time or "
     "high-throughput performance. The figures below are <b>design targets</b> for a typical student "
     "laptop, not measured benchmarks (except where noted), and are considered comfortably "
     "achievable given the small data size (about 1,800 projects per report).")
story.append(table(
    [["Aspect", "Target", "Notes"],
     ["Full extraction of one report", "Completes in a few minutes", "One-off batch step; ~114 data pages (May)."],
     ["Dataset size in memory", "Trivial (~1,800 rows x 13 cols)", "Well within pandas capacity on 4 GB RAM."],
     ["Model training", "Seconds to under a minute", "Simple classifier on a small dataset (planned)."],
     ["Single prediction / inference", "Under 1 second", "Interactive feel on the dashboard (planned)."],
     ["Dashboard page load", "Under 2–3 seconds", "Local server, small result set (planned)."],
     ["Concurrent users", "1 (single user)", "Not designed for multi-user load."]],
    [5.0 * cm, 5.0 * cm, CONTENT_W - 10.0 * cm], size=9.0))
gap(3)
H("Targets marked \"(planned)\" apply to modules not yet built and will be confirmed during testing.", Note)

H("4.2 Behavioral Description", H2)
para("UpTrack behaves as a sequence of discrete, mostly manual steps rather than an always-on service. "
     "It is deterministic: the same inputs produce the same outputs. Once a stage completes, its "
     "output becomes the input to the next stage. The system is idle between runs and performs work "
     "only when the user starts a stage (or opens the dashboard).")
H("4.2.1 System States", H3)
story.append(table(
    [["State", "What happens", "Moves to"],
     ["Idle", "Waiting; no processing.", "Extracting (user runs F1)"],
     ["Extracting", "Reading the PDF and building the dataset (F1).", "Preprocessing / Idle"],
     ["Preprocessing", "Cleaning and typing the data (F2).", "Matching / Feature prep"],
     ["Matching", "Linking projects across months (F3).", "Feature prep"],
     ["Feature prep", "Building features and labels (F4).", "Training"],
     ["Training", "Fitting the model, then evaluating (F5, F7).", "Serving / Idle"],
     ["Serving", "Dashboard shows results and answers user actions (F6).", "Idle (on close)"],
     ["Error", "A stage reports a failure and stops.", "Idle (after user fixes cause)"]],
    [3.2 * cm, CONTENT_W - 3.2 * cm - 4.4 * cm, 4.4 * cm], size=9.0))
H("4.2.2 Behaviour on Events and Invalid Input", H3)
bullets([
    "<b>Missing input file:</b> the affected stage stops immediately with a clear message and a "
    "non-zero exit status; no partial output is written as if it were complete.",
    "<b>Malformed / unparseable data:</b> the offending value is treated as missing and counted; "
    "the stage continues and reports the count.",
    "<b>Empty results in the dashboard:</b> a friendly \"no data\" message is shown instead of an error.",
    "<b>Repeated runs:</b> re-running a stage regenerates its output deterministically (idempotent).",
    "<b>User filter/search with no matches:</b> an empty list with an explanatory note is returned.",
])

H("4.3 Validation Criteria", H2)
para("The system is considered acceptable when the following criteria are met. Criteria for "
     "implemented stages are already enforced by the extraction stage's built-in validation report; "
     "criteria for planned stages define their acceptance in advance.")
H("4.3.1 Implemented — Data Extraction (enforced today)", H3)
bullets([
    "The output CSV has exactly <b>13 columns</b>.",
    "Every <font name=\"Courier\">project_row_id</font> is <b>unique</b>.",
    "<b>No</b> total, subtotal or grand-total rows leak into the data.",
    "Repeated serial numbers are recognised as expected (they restart per sector) and do not cause "
    "duplicate-key errors.",
    "Missing-value percentages per column are within expected bounds (sparse \"revised\" columns are "
    "allowed; core columns are near-complete).",
    "Data pages are read by structured table extraction, not the word-position fallback.",
    "The extraction program exits with a success status only when all of the above pass; otherwise it "
    "prints a warning and exits non-zero.",
])
H("4.3.2 Planned — Preprocessing, Model and Dashboard", H3)
bullets([
    "<b>Preprocessing:</b> all cost/time columns are numeric and all date columns parse; the "
    "converted/missing counts are reported.",
    "<b>Feature prep:</b> the feature matrix contains no unexpected missing values after the "
    "documented imputation, and no target-derived column is used as an input.",
    "<b>Model output:</b> every input project receives a label in {Likely Delayed, Likely On-Time} "
    "and a score in [0, 1].",
    "<b>Model quality (targets, TBD until measured):</b> the model should beat the majority-class "
    "baseline (about 54% on the current data) and report accuracy, precision, recall and F1 on the "
    "test set; a reasonable initial target is accuracy of at least 0.70, to be confirmed empirically.",
    "<b>Dashboard:</b> every project row shows a label and score; sector and risk filters and name "
    "search return correct results; empty and error states display a clear message.",
])

H("4.4 Non-Functional Requirements", H2)
story.append(table(
    [["ID", "Category", "Requirement"],
     ["NFR-1", "Usability", "Running a stage is a single command; the dashboard is readable by a non-technical viewer."],
     ["NFR-2", "Reliability", "Deterministic outputs; failures are explicit (clear message, non-zero exit), never silent."],
     ["NFR-3", "Maintainability", "Small, single-purpose modules with comments; clear separation of pipeline stages."],
     ["NFR-4", "Portability", "Runs on a standard PC with Python 3.13; no special hardware or OS features."],
     ["NFR-5", "Transparency", "Simple, interpretable model and features; every prediction has a score."],
     ["NFR-6", "Reproducibility", "Given the same PDFs and code, the dataset and results can be regenerated."],
     ["NFR-7", "Data integrity", "The system never fabricates data; missing source values stay missing."],
     ["NFR-8", "Performance", "Meets the modest targets of Section 4.1 on a typical laptop."]],
    [1.8 * cm, 3.2 * cm, CONTENT_W - 5.0 * cm], size=9.0))

H("4.5 Assumptions and Dependencies", H2)
bullets([
    "The MoSPI report PDFs keep a broadly consistent layout for Annexure XVIII across months; large "
    "format changes would need extractor adjustments.",
    "The report PDFs are available locally in <font name=\"Courier\">data/raw/</font> (the system does "
    "not download them).",
    "The delay label based on the reported time overrun is an acceptable ground truth for this "
    "educational project.",
    "Python 3.13 with pandas and pdfplumber is available; scikit-learn and a web framework will be "
    "installed for the planned stages.",
    "A single user operates the tool on one machine; no multi-user or deployment concerns apply.",
])

H("4.6 Limitations", H2)
bullets([
    "<b>Single report extracted so far:</b> only the May report is turned into data today; April "
    "extraction and cross-month matching are planned.",
    "<b>Extraction is source-dependent:</b> a few rows in the PDF are mangled and repaired by known "
    "patterns; an unseen anomaly could need a new rule. Three project names are genuinely absent in "
    "the source and are left blank by design.",
    "<b>Prediction is categorical:</b> UpTrack predicts risk (delayed or not), not the exact months "
    "of delay or exact cost overrun.",
    "<b>Model not yet trained:</b> no accuracy is claimed; quality will be known only after "
    "evaluation.",
    "<b>Educational scope:</b> results are for learning and demonstration, not for official or "
    "financial decisions.",
])

H("4.7 Error Handling", H2)
para("Error handling follows one principle: <b>fail loudly and never fabricate</b>. Concretely:")
bullets([
    "Missing input files stop the affected stage with a clear message and a non-zero exit status.",
    "Unparseable values become missing and are counted and reported, not guessed.",
    "The extraction stage keeps a skip log (with reasons) and a validation report, and warns when a "
    "check fails.",
    "The planned model falls back to the majority class and flags any record it cannot score.",
    "The planned dashboard shows friendly messages for empty results or bad input instead of crashing.",
])

H("4.8 Security and Privacy Considerations", H2)
para("UpTrack uses only <b>public government data about projects</b>; it stores <b>no personal data</b> "
     "about individuals, so data-privacy risk is minimal. The main considerations are integrity and "
     "safe local operation:")
bullets([
    "<b>No personal / sensitive data:</b> the dataset concerns public infrastructure projects only.",
    "<b>Local-only by default:</b> the planned dashboard runs on <font name=\"Courier\">localhost</font>; "
    "it is not exposed to the internet, so no authentication is required for this student scope.",
    "<b>Read-only source:</b> the original PDFs are never modified; the pipeline only reads them and "
    "writes new derived files.",
    "<b>Attribution and honesty:</b> the data source (MoSPI) is credited, and predictions are clearly "
    "labelled as model estimates, not official statements.",
    "<b>If ever deployed beyond localhost</b> (out of current scope), basic access control and input "
    "sanitisation would be required before sharing.",
])
story.append(PageBreak())


# ═════════════════════════════════════════════════════════════════════════════
#  5. VALIDATION & TESTING REQUIREMENTS
# ═════════════════════════════════════════════════════════════════════════════
H("5. Validation and Testing Requirements", H1)

H("5.1 Testing Approach", H2)
para("Testing follows the pipeline. Each stage is checked against the validation criteria of "
     "Section 4.3 before the next stage is trusted. The implemented extraction stage is tested by "
     "its own automated validation report; planned stages will be tested with small, targeted checks "
     "and manual spot-checks appropriate to a student project.")

H("5.2 Test Cases", H2)
story.append(table(
    [["ID", "What is tested", "Expected result", "Stage"],
     ["TC-1", "Extract May report", "1,817 rows, 13 columns, CSV written.", "F1 (impl.)"],
     ["TC-2", "Unique keys", "All project_row_id values unique.", "F1 (impl.)"],
     ["TC-3", "No total rows leak", "No total/subtotal/grand-total rows in data.", "F1 (impl.)"],
     ["TC-4", "Repeated serials", "Duplicate sl_no across sectors accepted, not an error.", "F1 (impl.)"],
     ["TC-5", "Missing-value profile", "Core columns near-complete; revised columns sparse as expected.", "F1 (impl.)"],
     ["TC-6", "Numeric casting", "Cost/time columns become numeric; bad values counted as missing.", "F2 (planned)"],
     ["TC-7", "Date parsing", "Month/year fields parse to dates; failures counted.", "F2 (planned)"],
     ["TC-8", "Cross-month matching", "Matched/new/dropped counts reported; sample verified.", "F3 (planned)"],
     ["TC-9", "No target leakage", "Overrun columns of target month absent from features.", "F4 (planned)"],
     ["TC-10", "Label correctness", "Delayed iff time overrun > 0.", "F4 (planned)"],
     ["TC-11", "Model output shape", "Every project gets a label and a score in [0,1].", "F5 (planned)"],
     ["TC-12", "Beats baseline", "Test accuracy above majority-class (~54%).", "F5/F7 (planned)"],
     ["TC-13", "Evaluation metrics", "Accuracy, precision, recall, F1, confusion matrix reported.", "F7 (planned)"],
     ["TC-14", "Dashboard display", "Projects, labels and scores shown; filters and search work.", "F6 (planned)"],
     ["TC-15", "Empty/error states", "Friendly message on missing results or no-match filter.", "F6 (planned)"]],
    [1.4 * cm, 4.7 * cm, CONTENT_W - 1.4 * cm - 4.7 * cm - 2.8 * cm, 2.8 * cm], size=8.8))

H("5.3 Acceptance Criteria", H2)
para("UpTrack is accepted for this laboratory when: (a) the extraction stage passes TC-1 to TC-5 "
     "automatically (already achieved for the May report); (b) the planned stages, once implemented, "
     "pass their test cases TC-6 to TC-15; and (c) the dashboard demonstrates a per-project "
     "delay-risk result end to end. Until the model is trained and evaluated, no specific accuracy "
     "figure is asserted; the target in Section 4.3 stands as a goal to be confirmed by measurement.")

gap(6)
story.append(HRule(CONTENT_W, RULE, 0.8))
gap(4)
H("Requirement Coverage Checklist (teacher's four required sections)", H2)
story.append(table(
    [["Required section", "Provided?", "Where"],
     ["1. Introduction — Goal &amp; Objectives of Software", "Yes", "Sections 1, 1.2"],
     ["2. Information Description — Problem Description", "Yes", "Section 2.1"],
     ["2. Information Description — Information Flow", "Yes", "Section 2.2, Figure 1"],
     ["2. Information Description — Hardware Interface", "Yes", "Section 2.5"],
     ["3. Functional Description — Process Narrative (each function)", "Yes", "Section 3.2 (F1–F7)"],
     ["4. Design Constraints — Performance Characteristics", "Yes", "Section 4.1"],
     ["4. Design Constraints — Behavioral Description", "Yes", "Section 4.2"],
     ["4. Design Constraints — Validation Criteria", "Yes", "Section 4.3"]],
    [8.8 * cm, 2.2 * cm, CONTENT_W - 11.0 * cm], align_center_cols=[1], size=9.0))
gap(10)
H("— End of Software Requirements Specification —", _st("end", parent=Small, fontName=F["body_i"]))


# ═════════════════════════════════════════════════════════════════════════════
#  DOC TEMPLATE, TOC WIRING, PAGE FOOTERS
# ═════════════════════════════════════════════════════════════════════════════
import copy

TOTAL = {"n": 0}


def on_page(canvas, doc):
    """Footer rule, left-hand text and 'Page X of N' on every page except the title."""
    canvas.saveState()
    if doc.page != 1:
        canvas.setStrokeColor(RULE); canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 1.45 * cm, A4[0] - MARGIN, 1.45 * cm)
        canvas.setFont(F["body"], 8); canvas.setFillColor(GREY)
        canvas.drawString(MARGIN, 1.02 * cm,
                          "UpTrack  |  Software Requirements Specification  |  Version 1.0")
        label = f"Page {doc.page}" + (f" of {TOTAL['n']}" if TOTAL['n'] else "")
        canvas.drawRightString(A4[0] - MARGIN, 1.02 * cm, label)
    canvas.restoreState()


class SRSDoc(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        try:
            name = flowable.style.name
        except AttributeError:
            return
        if name in ("H1", "H2", "H3"):
            level = {"H1": 0, "H2": 1, "H3": 2}[name]
            text = flowable.getPlainText()
            key = f"sec-{id(flowable)}"
            try:
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=level, closed=(level > 0))
            except Exception:
                pass
            self.notify("TOCEntry", (level, text, self.page, key))


def make_doc(target):
    # `target` may be a path string or a writable file-like object.
    return SRSDoc(target, pagesize=A4,
                  leftMargin=MARGIN, rightMargin=MARGIN,
                  topMargin=2.0 * cm, bottomMargin=1.9 * cm,
                  title="UpTrack — Software Requirements Specification",
                  author="UpTrack project", subject="SRS")


if __name__ == "__main__":
    # Pass 1 (throwaway): count total pages so the footer can show "Page X of N".
    # A deep copy is built here so the real flowables stay pristine for pass 2.
    counter = make_doc(BytesIO())
    counter.multiBuild(copy.deepcopy(story), onFirstPage=on_page, onLaterPages=on_page)
    TOTAL["n"] = counter.page

    # Pass 2 (real file): normal canvas, so bookmark destinations resolve correctly.
    doc = make_doc(str(OUT))
    doc.multiBuild(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"Wrote {OUT}  ({doc.page} pages)")
