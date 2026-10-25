"""Generate real sample PDFs, extract them and check what the model will see."""

from datetime import date

import pytest

from app.ingestion.chunking import chunk_contract
from app.ingestion.pdf_extract import extract_pages
from sample_contracts.builder import build_all
from sample_contracts.pdf_writer import write_contract_pdf

TODAY = date(2026, 10, 24)


@pytest.fixture(scope="module")
def documents():
    return {d.contract_id: d for d in build_all(TODAY)}


def _extract(doc, tmp_path):
    path = tmp_path / doc.file_name
    pages_written = write_contract_pdf(doc, path)
    pages = extract_pages(path)
    assert len(pages) == pages_written
    return pages


def test_dates_are_relative_to_today(documents):
    assert documents["C-001"].expiration_date == date(2026, 11, 13)   # 20 days ahead
    assert documents["C-005"].expiration_date < TODAY                  # already expired


def test_supply_agreement_round_trip(documents, tmp_path):
    doc = documents["C-003"]
    pages = _extract(doc, tmp_path)
    assert not any("CONFIDENTIAL" in p.markdown or "Page 1 of" in p.markdown for p in pages)

    chunks = chunk_contract(pages, doc.contract_id, doc.title, doc.counterparty.name)
    numbers = [c.clause_number for c in chunks if c.clause_number]
    assert numbers == [str(n) for n in range(1, len(doc.clauses) + 1)]

    termination = next(c for c in chunks if c.heading == "Termination")
    assert (termination.page_start, termination.page_end) == (2, 3)   # the clause crosses a page break


def test_nda_has_no_termination_wording(documents, tmp_path):
    pages = _extract(documents["C-004"], tmp_path)
    assert "terminat" not in " ".join(p.markdown for p in pages).lower()
