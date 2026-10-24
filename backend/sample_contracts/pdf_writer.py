"""Render a ContractDocument as a realistic-looking PDF (fpdf2, A4)."""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .builder import ContractDocument, Paragraph, format_date

FONT = "Helvetica"
BODY_SIZE = 10
LINE_H = 5.0
SUB_LABEL_W = 11   # width of the "8.1" label column (mm)
ITEM_LABEL_W = 8   # width of the "(a)" label column (mm)
GREY = 110

_ITEM_LABEL = re.compile(r"^(\([a-z]{1,3}\))\s+(.*)$")


class ContractPDF(FPDF):
    def __init__(self, doc: ContractDocument):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.doc = doc
        self.set_margins(left=22, top=24, right=22)
        self.set_auto_page_break(auto=True, margin=22)
        self.set_title(doc.title)
        self.set_author(doc.company.name)
        self.set_subject(f"{doc.contract_id} - {doc.counterparty.name}")
        self.set_creator("ai-contract-assistant sample generator")

    # Running header and footer (the extractor must cope with these).
    def header(self):
        self.set_y(11)
        self.set_font(FONT, "", 8)
        self.set_text_color(GREY)
        self.cell(0, 4, "CONFIDENTIAL", align="L")
        self.set_x(self.l_margin)
        self.cell(0, 4, f"Ref. {self.doc.contract_id}  |  {self.doc.counterparty.name}", align="R")
        self.set_draw_color(190)
        self.line(self.l_margin, 16.5, self.w - self.r_margin, 16.5)
        self.set_text_color(0)
        self.set_y(self.t_margin)

    def footer(self):
        self.set_y(-14)
        self.set_font(FONT, "", 8)
        self.set_text_color(GREY)
        self.cell(0, 4, f"Page {self.page_no()} of {{nb}}", align="C")
        self.set_text_color(0)

    # Building blocks -------------------------------------------------
    def text_block(self, text: str, x: float | None = None, size: float = BODY_SIZE, style: str = ""):
        self.set_font(FONT, style, size)
        self.set_x(self.l_margin if x is None else x)
        self.multi_cell(0, LINE_H, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def section_title(self, text: str):
        if self.will_page_break(LINE_H * 4):
            self.add_page()
        self.ln(3)
        self.set_font(FONT, "B", 11)
        self.cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def labelled(self, label: str, text: str, indent: float, label_w: float):
        """A paragraph with a hanging label, e.g. '8.1  The Provider shall...'."""
        self.set_font(FONT, "", BODY_SIZE)
        self.set_x(self.l_margin + indent)
        self.cell(label_w, LINE_H, label)
        self.multi_cell(0, LINE_H, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def paragraph(self, label: str, para: Paragraph):
        indent = SUB_LABEL_W if label else 0
        if label:
            self.labelled(label, para.text, 0, SUB_LABEL_W)
        else:
            self.text_block(para.text)
        for item in para.items:
            self.ln(0.8)
            m = _ITEM_LABEL.match(item)
            if m:
                self.labelled(m.group(1), m.group(2), indent + 4, ITEM_LABEL_W)
            else:
                self.text_block(item, x=self.l_margin + indent + 4)
        self.ln(1.8)

    # Document sections -------------------------------------------------
    def title_page(self):
        d = self.doc
        self.set_font(FONT, "B", 17)
        self.multi_cell(0, 8, d.title.upper(), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)
        self.set_font(FONT, "", 9)
        self.set_text_color(GREY)
        self.cell(0, 5, f"Contract reference {d.contract_id}", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0)
        self.ln(6)
        self.text_block(f'THIS AGREEMENT is dated {format_date(d.effective_date)} (the "Effective Date").')
        self.section_title("PARTIES")
        for i, party in enumerate((d.company, d.counterparty), start=1):
            ending = "; and" if i == 1 else "."
            self.labelled(f"({i})", f'{party.name}, {party.description} (the "{party.role}"){ending}', 0, ITEM_LABEL_W)
            self.ln(1)
        self.section_title("BACKGROUND")
        for i, recital in enumerate(d.recitals):
            self.labelled(f"({chr(ord('A') + i)})", recital, 0, ITEM_LABEL_W)
            self.ln(1)
        self.section_title("AGREED TERMS")

    def clauses(self):
        for clause in self.doc.clauses:
            self.section_title(f"{clause.number}. {clause.heading}")
            numbered = len(clause.paragraphs) > 1
            for i, para in enumerate(clause.paragraphs, start=1):
                self.paragraph(f"{clause.number}.{i}" if numbered else "", para)

    def signatures(self):
        d = self.doc
        if self.will_page_break(75):
            self.add_page()
        self.ln(4)
        self.text_block(
            "IN WITNESS WHEREOF the parties have signed this Agreement on the Effective Date "
            "by their duly authorised representatives."
        )
        for party in (d.company, d.counterparty):
            self.ln(6)
            self.text_block(f"Signed for and on behalf of {party.name}", style="B")
            self.ln(7)
            y = self.get_y()
            self.set_draw_color(120)
            self.line(self.l_margin, y, self.l_margin + 70, y)
            self.ln(1.5)
            self.text_block(f"Name: {party.signatory}")
            self.text_block(f"Title: {party.signatory_title}")
            self.text_block(f"Date: {format_date(d.effective_date)}")


def write_contract_pdf(doc: ContractDocument, path: Path) -> int:
    """Write the PDF and return its page count."""
    pdf = ContractPDF(doc)
    pdf.add_page()
    pdf.title_page()
    pdf.clauses()
    pdf.signatures()
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return pdf.page_no()
