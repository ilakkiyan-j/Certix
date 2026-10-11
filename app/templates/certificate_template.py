import uuid
from datetime import date
from pathlib import Path
from typing import BinaryIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas


class CertificateTemplate:
    """Renders a high-quality, professional landscape certificate PDF."""

    PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)

    # Design System Color Tokens
    COLOR_CANVAS = colors.HexColor("#FAFAFC")
    COLOR_GOLD_PRIMARY = colors.HexColor("#C59B27")
    COLOR_GOLD_LIGHT = colors.HexColor("#E5C158")
    COLOR_NAVY_PRIMARY = colors.HexColor("#0F172A")
    COLOR_SLATE_DARK = colors.HexColor("#1E293B")
    COLOR_SLATE_MUTED = colors.HexColor("#475569")
    COLOR_SLATE_LIGHT = colors.HexColor("#94A3B8")

    @classmethod
    def render(
        cls,
        output: str | Path | BinaryIO,
        recipient_name: str,
        event_name: str,
        completion_date: date,
        certificate_id: uuid.UUID,
    ) -> None:
        """Render the complete certificate PDF document."""
        pdf_canvas = canvas.Canvas(
            str(output) if isinstance(output, Path) else output,
            pagesize=(cls.PAGE_WIDTH, cls.PAGE_HEIGHT),
        )

        cls._draw_background(pdf_canvas)
        cls._draw_borders_and_ornaments(pdf_canvas)
        cls._draw_header(pdf_canvas)
        cls._draw_recipient(pdf_canvas, recipient_name)
        cls._draw_event_details(pdf_canvas, event_name, completion_date)
        cls._draw_footer(pdf_canvas, certificate_id, completion_date)

        pdf_canvas.showPage()
        pdf_canvas.save()

    @classmethod
    def _draw_background(cls, c: canvas.Canvas) -> None:
        """Draw certificate canvas background."""
        c.setFillColor(cls.COLOR_CANVAS)
        c.rect(0, 0, cls.PAGE_WIDTH, cls.PAGE_HEIGHT, fill=1, stroke=0)

    @classmethod
    def _draw_borders_and_ornaments(cls, c: canvas.Canvas) -> None:
        """Draw elegant double gold border and corner bracket ornaments."""
        # Outer Border
        c.setStrokeColor(cls.COLOR_GOLD_PRIMARY)
        c.setLineWidth(2.5)
        c.rect(26, 26, cls.PAGE_WIDTH - 52, cls.PAGE_HEIGHT - 52)

        # Inner Border
        c.setStrokeColor(cls.COLOR_GOLD_LIGHT)
        c.setLineWidth(1.0)
        c.rect(33, 33, cls.PAGE_WIDTH - 66, cls.PAGE_HEIGHT - 66)

        # Corner Accents (L-brackets at corners)
        c.setStrokeColor(cls.COLOR_NAVY_PRIMARY)
        c.setLineWidth(3.0)
        bracket_len = 18

        # Top-Left
        c.line(20, cls.PAGE_HEIGHT - 20, 20 + bracket_len, cls.PAGE_HEIGHT - 20)
        c.line(20, cls.PAGE_HEIGHT - 20, 20, cls.PAGE_HEIGHT - 20 - bracket_len)

        # Top-Right
        c.line(
            cls.PAGE_WIDTH - 20,
            cls.PAGE_HEIGHT - 20,
            cls.PAGE_WIDTH - 20 - bracket_len,
            cls.PAGE_HEIGHT - 20,
        )
        c.line(
            cls.PAGE_WIDTH - 20,
            cls.PAGE_HEIGHT - 20,
            cls.PAGE_WIDTH - 20,
            cls.PAGE_HEIGHT - 20 - bracket_len,
        )

        # Bottom-Left
        c.line(20, 20, 20 + bracket_len, 20)
        c.line(20, 20, 20, 20 + bracket_len)

        # Bottom-Right
        c.line(cls.PAGE_WIDTH - 20, 20, cls.PAGE_WIDTH - 20 - bracket_len, 20)
        c.line(cls.PAGE_WIDTH - 20, 20, cls.PAGE_WIDTH - 20, 20 + bracket_len)

    @classmethod
    def _draw_header(cls, c: canvas.Canvas) -> None:
        """Draw header and institution titles."""
        center_x = cls.PAGE_WIDTH / 2.0

        # Sub-header / Badge
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(cls.COLOR_GOLD_PRIMARY)
        c.drawCentredString(
            center_x, cls.PAGE_HEIGHT - 75, "★  OFFICIAL CERTIFICATION OF ACHIEVEMENT  ★"
        )

        # Main Certificate Title
        c.setFont("Helvetica-Bold", 28)
        c.setFillColor(cls.COLOR_NAVY_PRIMARY)
        c.drawCentredString(center_x, cls.PAGE_HEIGHT - 115, "CERTIFICATE OF COMPLETION")

        # Decorative Divider Line
        c.setStrokeColor(cls.COLOR_GOLD_PRIMARY)
        c.setLineWidth(1.5)
        c.line(center_x - 80, cls.PAGE_HEIGHT - 128, center_x + 80, cls.PAGE_HEIGHT - 128)

        # Presentation lead text
        c.setFont("Helvetica", 12)
        c.setFillColor(cls.COLOR_SLATE_MUTED)
        c.drawCentredString(center_x, cls.PAGE_HEIGHT - 165, "THIS IS PROUDLY PRESENTED TO")

    @classmethod
    def _draw_recipient(cls, c: canvas.Canvas, recipient_name: str) -> None:
        """Draw recipient name with dynamic auto-scaling to prevent overflow."""
        center_x = cls.PAGE_WIDTH / 2.0
        y_pos = cls.PAGE_HEIGHT - 215

        # Dynamic font scaling based on name length
        name_len = len(recipient_name)
        if name_len > 40:
            font_size = 18
        elif name_len > 28:
            font_size = 22
        elif name_len > 20:
            font_size = 25
        else:
            font_size = 28

        c.setFont("Helvetica-Bold", font_size)
        c.setFillColor(cls.COLOR_NAVY_PRIMARY)
        c.drawCentredString(center_x, y_pos, recipient_name)

        # Underline accent for recipient name
        c.setStrokeColor(cls.COLOR_GOLD_LIGHT)
        c.setLineWidth(1.0)
        text_width = c.stringWidth(recipient_name, "Helvetica-Bold", font_size)
        line_half = max(text_width / 2.0 + 15, 100)
        c.line(center_x - line_half, y_pos - 8, center_x + line_half, y_pos - 8)

    @classmethod
    def _draw_event_details(cls, c: canvas.Canvas, event_name: str, completion_date: date) -> None:
        """Draw achievement text and event details."""
        center_x = cls.PAGE_WIDTH / 2.0

        c.setFont("Helvetica", 12)
        c.setFillColor(cls.COLOR_SLATE_MUTED)
        c.drawCentredString(
            center_x,
            cls.PAGE_HEIGHT - 260,
            "for successfully completing and demonstrating mastery in",
        )

        # Event Name
        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(cls.COLOR_SLATE_DARK)
        c.drawCentredString(center_x, cls.PAGE_HEIGHT - 295, event_name)

    @classmethod
    def _draw_footer(
        cls, c: canvas.Canvas, certificate_id: uuid.UUID, completion_date: date
    ) -> None:
        """Draw footer with date, signature line, seal emblem, and verification certificate ID."""
        center_x = cls.PAGE_WIDTH / 2.0
        footer_y = 110

        # Date formatting
        date_str = completion_date.strftime("%B %d, %Y")

        # Left Column: Date of Issue
        c.setFont("Helvetica", 10)
        c.setFillColor(cls.COLOR_SLATE_MUTED)
        c.drawString(90, footer_y + 15, "DATE OF ISSUANCE")
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(cls.COLOR_NAVY_PRIMARY)
        c.drawString(90, footer_y - 2, date_str)
        c.setStrokeColor(cls.COLOR_SLATE_LIGHT)
        c.setLineWidth(0.8)
        c.line(90, footer_y + 10, 230, footer_y + 10)

        # Center Column: Verification Seal Emblem
        c.setStrokeColor(cls.COLOR_GOLD_PRIMARY)
        c.setLineWidth(2.0)
        c.circle(center_x, footer_y + 15, 26, stroke=1, fill=0)
        c.setLineWidth(0.8)
        c.circle(center_x, footer_y + 15, 22, stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(cls.COLOR_GOLD_PRIMARY)
        c.drawCentredString(center_x, footer_y + 17, "CERTIX")
        c.drawCentredString(center_x, footer_y + 8, "VERIFIED")

        # Right Column: Authorized Signatory
        c.setFont("Helvetica", 10)
        c.setFillColor(cls.COLOR_SLATE_MUTED)
        c.drawRightString(cls.PAGE_WIDTH - 90, footer_y + 15, "AUTHORIZED SIGNATURE")
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(cls.COLOR_NAVY_PRIMARY)
        c.drawRightString(cls.PAGE_WIDTH - 90, footer_y - 2, "Certix Certification Board")
        c.setStrokeColor(cls.COLOR_SLATE_LIGHT)
        c.setLineWidth(0.8)
        c.line(cls.PAGE_WIDTH - 230, footer_y + 10, cls.PAGE_WIDTH - 90, footer_y + 10)

        # Bottom Verification Hash / ID
        c.setFont("Helvetica", 8)
        c.setFillColor(cls.COLOR_SLATE_LIGHT)
        c.drawCentredString(
            center_x,
            46,
            f"Certificate ID: {certificate_id}  •  Verify authenticity via Certix Network",
        )
