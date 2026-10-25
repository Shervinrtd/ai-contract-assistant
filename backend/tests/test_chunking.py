"""Clause chunking, page ranges and header/footer removal (no PDF needed)."""

import pytest

from app.ingestion.chunking import chunk_contract, match_clause_heading
from app.ingestion.pdf_extract import PageText, remove_repeated_lines

PAGES = [
    PageText(1, "# **TEST AGREEMENT**\n\nTHIS AGREEMENT is dated 1 January 2026.\n\n"
                "## **1. Definitions**\n\nIn this Agreement the following definitions apply.\n\n"
                "## **2. Termination**\n\n- 2.1 Either party may terminate on ninety (90) days' notice."),
    PageText(2, "- 2.2 Either party may terminate for material breach.\n\n"
                "## **3. Notices**\n\n- 3.1 Notices must be in writing.\n\n"
                "IN WITNESS WHEREOF the parties have signed this Agreement.\n\nName: A. Person"),
]


def test_one_chunk_per_clause_plus_preamble_and_signatures():
    chunks = chunk_contract(PAGES, "C-009", "Test Agreement", "Acme S.p.A.")
    assert [c.chunk_id for c in chunks] == [
        "C-009:parties-and-background", "C-009:1", "C-009:2", "C-009:3", "C-009:signatures",
    ]


def test_clause_spanning_a_page_break_keeps_its_page_range():
    termination = next(c for c in chunk_contract(PAGES, "C-009", "Test Agreement", "Acme S.p.A.") if c.clause_number == "2")
    assert (termination.page_start, termination.page_end) == (1, 2)
    assert "2.2" in termination.text and "3.1" not in termination.text
    assert termination.citation == "Test Agreement (C-009), clause 2, pp. 1-2"


def test_search_text_carries_contract_and_heading():
    clause = chunk_contract(PAGES, "C-009", "Test Agreement", "Acme S.p.A.")[2]
    assert clause.search_text.startswith("Contract: Test Agreement with Acme S.p.A. (C-009)\nSection: 2. Termination")


@pytest.mark.parametrize(
    "line, expected",
    [
        ("## **8. Termination**", ("8", "Termination")),
        ("**12. Governing Law and Jurisdiction**", ("12", "Governing Law and Jurisdiction")),
        ("8. Termination", ("8", "Termination")),
        ("- 8.1 Either party may terminate this Agreement.", None),  # sub-clause, not a heading
        ("8. This sentence is body text and ends with a period.", None),
    ],
)
def test_clause_heading_detection(line, expected):
    assert match_clause_heading(line) == expected


def test_running_headers_and_footers_are_removed():
    bodies = ["Alpha clause text.", "Beta clause text.", "Gamma clause text."]
    pages = [PageText(i, f"CONFIDENTIAL\n\n{body}\n\nPage {i} of 3") for i, body in enumerate(bodies, start=1)]
    for page, body in zip(remove_repeated_lines(pages), bodies):
        assert page.markdown == body
