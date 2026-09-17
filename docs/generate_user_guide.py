#!/usr/bin/env python3
"""Generate the downloadable student PDF guide for the Lab Scheduler portal.

Run this whenever the on-screen flow changes (new fields, renamed buttons,
updated screenshots, etc.) to keep the guide in sync:

    pip install reportlab
    python3 docs/generate_user_guide.py

Output: assets/Lab_Scheduler_Student_Guide.pdf
The file lands in assets/ so it's served automatically at
/assets/Lab_Scheduler_Student_Guide.pdf (already mounted by app.py) and is
copied into the Docker image by the existing `COPY assets/ assets/` step —
no application code changes are needed to publish an update.
"""
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
IMG = os.path.join(ROOT, "docs", "img")
OUT = os.path.join(ASSETS, "Lab_Scheduler_Student_Guide.pdf")

GREEN = colors.HexColor("#01a982")
DARK = colors.HexColor("#122229")
GRAY = colors.HexColor("#5b6b72")
LIGHTBG = colors.HexColor("#eef7f5")
BORDER = colors.HexColor("#d7e4e2")

styles = getSampleStyleSheet()

kicker = ParagraphStyle(
    "Kicker", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9,
    textColor=GREEN, spaceAfter=6, tracking=1,
)
title = ParagraphStyle(
    "TitleBig", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=26,
    textColor=DARK, leading=30, spaceAfter=4,
)
subtitle = ParagraphStyle(
    "Subtitle", parent=styles["Normal"], fontSize=12.5, textColor=GRAY,
    leading=17, spaceAfter=2,
)
h2 = ParagraphStyle(
    "H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15,
    textColor=DARK, spaceBefore=18, spaceAfter=8,
)
h3 = ParagraphStyle(
    "H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=12,
    textColor=GREEN, spaceBefore=10, spaceAfter=4,
)
body = ParagraphStyle(
    "Body", parent=styles["Normal"], fontSize=10.5, leading=15.5,
    textColor=DARK, spaceAfter=6, alignment=TA_LEFT,
)
small = ParagraphStyle(
    "Small", parent=body, fontSize=9, textColor=GRAY, leading=13,
)
caption = ParagraphStyle(
    "Caption", parent=styles["Normal"], fontSize=9, textColor=GRAY,
    alignment=TA_CENTER, spaceBefore=4, spaceAfter=14, fontName="Helvetica-Oblique",
)
step = ParagraphStyle(
    "Step", parent=body, spaceAfter=5,
)
tablehead = ParagraphStyle(
    "TableHead", parent=body, fontName="Helvetica-Bold", textColor=colors.white,
    fontSize=10.5, spaceAfter=0,
)
tablecell = ParagraphStyle(
    "TableCell", parent=body, fontSize=9.5, spaceAfter=0, leading=13,
)


def bullets(items, style=body, bullet_color=GREEN):
    return ListFlowable(
        [ListItem(Paragraph(t, style), bulletColor=bullet_color, spaceAfter=4)
         for t in items],
        bulletType="bullet", start="circle", leftIndent=16,
    )


def numbered(items):
    return ListFlowable(
        [ListItem(Paragraph(t, step), spaceAfter=8) for t in items],
        bulletType="1", leftIndent=18,
    )


def screenshot(path, max_width, caption_text):
    img = Image(path)
    ratio = img.imageHeight / float(img.imageWidth)
    img.drawWidth = max_width
    img.drawHeight = max_width * ratio
    img.hAlign = "CENTER"
    return KeepTogether([
        Spacer(1, 4),
        img,
        Paragraph(caption_text, caption),
    ])


def callout(text_lines):
    rows = [[Paragraph(t, body)] for t in text_lines]
    t = Table(rows, colWidths=[6.4 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHTBG),
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def build():
    doc = SimpleDocTemplate(
        OUT, pagesize=LETTER,
        topMargin=0.65 * inch, bottomMargin=0.65 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        title="Self-Driving Labs — Student Guide",
        author="HPE Networking · Technical Readiness & Innovation Group",
    )
    story = []

    # Header
    logo = Image(os.path.join(ASSETS, "hpelogo.png"))
    logo.drawWidth = 1.3 * inch
    logo.drawHeight = 1.3 * inch * (logo.imageHeight / float(logo.imageWidth))
    story.append(logo)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "HPE NETWORKING &nbsp;·&nbsp; TECHNICAL READINESS &amp; INNOVATION GROUP",
        kicker))
    story.append(Paragraph("Self-Driving Labs", title))
    story.append(Paragraph("Student guide — reserving a hands-on lab session", subtitle))
    story.append(Spacer(1, 4))
    hr = Table([[""]], colWidths=[6.9 * inch], rowHeights=[2])
    hr.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN)]))
    story.append(Spacer(1, 8))
    story.append(hr)
    story.append(Spacer(1, 10))

    # Overview
    story.append(Paragraph(
        "The Self-Driving Labs portal is a no-login web page where you can browse "
        "upcoming hands-on lab sessions and grab a seat, or schedule a brand-new "
        "session of your own. This guide walks through both paths. Ask your "
        "instructor or program contact for the portal link if you don't already "
        "have it.", body))

    story.append(Paragraph("Two ways to get a seat", h2))
    tbl_data = [
        [Paragraph("<b>Join a Workshop</b>", tablehead), Paragraph("<b>Sign up for a New Workshop</b>", tablehead)],
        [Paragraph(
            "Add yourself to a session someone else already scheduled. Fastest "
            "option — the course, date, time, and time zone are already set.",
            tablecell),
         Paragraph(
            "Create a brand-new session for a course that isn't on the calendar "
            "yet, or at a time that works better for you. You choose the course, "
            "date/time, and time zone.", tablecell)],
    ]
    tbl = Table(tbl_data, colWidths=[3.2 * inch, 3.2 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHTBG),
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.75, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6))

    story.append(Paragraph("Before you start", h2))
    story.append(bullets([
        "Your email address — used to confirm the reservation and add you to the session.",
        "If joining: nothing else to prepare — just find a session on the calendar.",
        "If scheduling a new session: know which course you want and roughly when "
        "you'd like it, plus your time zone.",
    ]))

    story.append(screenshot(
        os.path.join(IMG, "welcome.png"), 4.6 * inch,
        "The welcome page — choose \u201cJoin a Workshop\u201d or \u201cSign up for a New Workshop\u201d."))

    # Option A
    story.append(Paragraph("Option A — Join an Existing Workshop", h2))
    story.append(numbered([
        "From the welcome page, click <b>Join a Workshop</b>.",
        "You'll see a calendar of upcoming sessions. Each colored tile is a scheduled "
        "workshop, showing its course code, start time, and seats remaining.",
        "Click any day that has sessions to open the day's detail list.",
        "In the list, click the workshop you want to join. Full sessions are grayed "
        "out and can't be selected.",
        "On the join form, your course, reservation ID, start/end time, and time "
        "zone are already filled in and locked — just enter your email address "
        "and an optional comment.",
        "Click <b>Join this workshop →</b>. You'll land on a confirmation page "
        "showing whether the reservation succeeded, along with the reservation "
        "details.",
    ]))

    story.append(screenshot(
        os.path.join(IMG, "day-modal.png"), 5.6 * inch,
        "Day detail view — click a workshop to join it (full sessions are dimmed)."))

    # Option B
    story.append(Paragraph("Option B — Sign Up for a New Workshop", h2))
    story.append(numbered([
        "From the welcome page, click <b>Sign up for a New Workshop</b>.",
        "You'll see the same calendar, marked with a “+” on days you can schedule "
        "into. Click a day to preview what's already booked that day, then click "
        "<b>Continue to sign up →</b>.",
        "On the form, choose your <b>course</b> from the dropdown.",
        "Pick a <b>start date &amp; time</b> using the date picker. The session's "
        "end time is set automatically (a fixed number of hours after the start — "
        "check the note under the field for the exact duration).",
        "Choose your <b>time zone</b> from the dropdown — it defaults to the "
        "portal's standard zone, but you can pick your own.",
        "Enter your <b>email address</b> and an optional note for the lab team, "
        "then click <b>Reserve this lab →</b>.",
        "You'll land on a confirmation page showing whether the new session was "
        "created, along with the reservation details.",
    ]))

    story.append(screenshot(
        os.path.join(IMG, "calendar.png"), 5.6 * inch,
        "New-workshop calendar — click a day, then continue to the sign-up form."))

    # Course codes
    story.append(Paragraph("Understanding course codes", h2))
    story.append(Paragraph(
        "Each session is labeled with a short course code such as "
        "<font face='Courier-Bold'>TE1-101.a</font> or "
        "<font face='Courier-Bold'>TE4-203.b</font>. The prefix (TE1, TE2, TE3…) "
        "groups related courses by curriculum family (for example, Campus "
        "Networking, Aruba Central, Data Center Networking). On the calendar page, "
        "open the <b>“Course code legend”</b> panel above the calendar to see "
        "the full list of codes and what each one stands for.", body))

    # Time zones
    story.append(Paragraph("Time zones &amp; session length", h2))
    story.append(bullets([
        "When <b>joining</b>, the time shown is exactly as scheduled — the time "
        "zone field is locked so there's no mix-up.",
        "When creating a <b>new</b> session, pick the time zone that makes sense "
        "for you (or your students, if you're scheduling on their behalf). "
        "Double-check it before submitting — this is the most common source of "
        "confusion.",
        "New sessions run for a fixed number of hours after the start time you "
        "choose (shown on the form). You don't set an end time directly.",
    ]))

    # After you submit
    story.append(Paragraph("After you submit", h2))
    story.append(Paragraph(
        "Every submission — join or new — takes you straight to a result page "
        "that tells you immediately whether it worked, along with a summary of "
        "the course, reservation ID, start/end time, time zone, and the email "
        "used. If something goes wrong (for example the session filled up while "
        "you were on the form), the page explains that and lets you pick another "
        "session without starting over.", body))

    # Tips
    story.append(Paragraph("Tips &amp; troubleshooting", h2))
    story.append(callout([
        "<b>A session shows “Full”</b> — someone else took the last seat. Pick a "
        "different time slot, or use “Sign up for a New Workshop” to schedule "
        "another session of the same course.",
        "<b>Wrong time zone on a new session</b> — double check the time-zone "
        "dropdown before submitting; it can't be changed afterward without "
        "contacting the lab team.",
        "<b>Didn't get a confirmation</b> — check the reservation ID shown on the "
        "result page and hold onto it; reach out to your lab administrator with "
        "that ID if anything looks off.",
        "<b>Calendar looks empty</b> — try a day further out; sessions are "
        "scheduled on a rolling basis a few weeks ahead.",
    ]))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Need help? Contact your instructor or lab administrator — include the "
        "reservation ID from your confirmation page if you have one.", small))
    story.append(Paragraph("Powered by the vLab scheduler.", small))

    doc.build(story)


if __name__ == "__main__":
    build()
    print(f"Wrote {OUT}")
