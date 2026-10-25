"""The citation check: only ids that came back from a tool survive, renumbered [1], [2]..."""

import pytest

from app.agent import _Evidence, apply_citations


@pytest.fixture
def evidence():
    ev = _Evidence()
    ev.collect({"contracts": [{"id": "C-001", "title": "SaaS Subscription Agreement"}]})
    ev.collect({"results": [{
        "chunk_id": "C-003:8", "contract_id": "C-003", "contract_title": "Master Supply Agreement",
        "clause_number": "8", "heading": "Termination", "page_start": 2, "page_end": 3,
        "citation": "Master Supply Agreement (C-003), clause 8, pp. 2-3", "score": 0.54,
        "text": "## 8. Termination\n\n- 8.1 Either party may terminate for convenience on ninety (90) days' notice.",
    }]})
    return ev


def test_valid_markers_are_numbered_by_first_appearance(evidence):
    text, citations, warnings = apply_citations("A [C-003:8]. B [C-001]. Again [C-003:8].", evidence)
    assert text == "A [1]. B [2]. Again [1]."
    assert [c.source_id for c in citations] == ["C-003:8", "C-001"]
    assert citations[0].pdf_url == "/contracts/C-003/pdf#page=2"
    assert citations[0].label == "Master Supply Agreement (C-003), clause 8, pp. 2-3"
    assert citations[0].quote.startswith("8.1 Either party may terminate")
    assert citations[1].kind == "contract" and citations[1].pdf_url == "/contracts/C-001/pdf"
    assert warnings == []


def test_invented_ids_are_removed_and_reported(evidence):
    text, citations, warnings = apply_citations("Fact [C-042]. Other [C-003:99].", evidence)
    assert text == "Fact. Other."
    assert citations == []
    assert len(warnings) == 2 and "C-042" in warnings[0]


def test_several_ids_in_one_bracket(evidence):
    text, citations, _ = apply_citations("Both apply [C-003:8, C-001].", evidence)
    assert text == "Both apply [1][2]."
    assert len(citations) == 2


def test_ordinary_brackets_are_left_alone(evidence):
    text, citations, warnings = apply_citations("See the [optional] note.", evidence)
    assert text == "See the [optional] note."
    assert citations == [] and warnings == []
